#!/usr/bin/env python3
"""ReelReady cut engine — dead air, fillers and retakes -> an edit decision list (EDL).

    python3 engines/cut.py <clip> --transcript transcript.json --out edl.json
        [--keep-hook-seconds 2] [--silence-db -35] [--min-gap 0.45]

Output:
    {"source": "/abs/clip.mp4", "duration": 20.0, "hook_seconds": 2.0,
     "keep":    [{"start": 0.0, "end": 4.7, "reason": "speech"}, ...],
     "removed": [{"start": 4.7, "end": 5.6, "reason": "dead-air|filler|retake", "detail": "..."}, ...],
     "stats":   {...}}

How it decides (logic adapted from the yt-edit skill's deadair.py):
  dead-air  ffmpeg silencedetect runs longer than --min-gap, trimmed from the MIDDLE so each side
            keeps a short breath (cutting flush against speech sounds gasping).
  filler    um/uh/er/hmm always; "like", "so", "you know", "I mean" only when they stand alone
            (set off by a comma or a pause) so real uses ("I like coffee") survive.
  retake    a sentence followed within the next two sentences by a near-duplicate of itself:
            the EARLIER take is removed, the last take is kept.
  hook      nothing is ever cut inside the first --keep-hook-seconds.
This never touches media. render_cut.py applies the EDL.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # keep engines/ free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _media import need, video_info  # noqa: E402

ALWAYS_FILLER = {"um", "umm", "uh", "uhh", "uhm", "er", "erm", "ah", "hmm", "mm", "mhm"}
SOFT_FILLER = {"like", "so"}            # filler only when set off by punctuation or a pause
SOFT_PHRASES = [("you", "know"), ("i", "mean")]
BREATH = 0.12                           # seconds of air kept each side of a dead-air cut
PRIORITY = {"retake": 3, "filler": 2, "dead-air": 1}


def norm(w: str) -> str:
    return re.sub(r"[^a-z']", "", w.lower())


def silences(clip: str, db: float, min_gap: float) -> list[tuple[float, float]]:
    need("ffmpeg")
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", clip, "-vn", "-af",
                        f"silencedetect=noise={db}dB:d={min_gap}", "-f", "null", "-"],
                       capture_output=True, text=True)
    out, start = [], None
    for line in p.stderr.splitlines():
        m = re.search(r"silence_start: (-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and start is not None:
            out.append((start, float(m.group(1))))
            start = None
    if start is not None:                     # silence runs to the end of the file
        out.append((start, float("inf")))
    return out


def find_fillers(words: list[dict]) -> list[dict]:
    cuts = []
    n = len(words)
    for i, w in enumerate(words):
        t = norm(w["w"])
        prev_end = words[i - 1]["end"] if i else -1.0
        prev_txt = words[i - 1]["w"] if i else "."
        if t in ALWAYS_FILLER:
            cuts.append({"start": w["start"], "end": w["end"], "reason": "filler", "detail": w["w"]})
            continue
        if t in SOFT_FILLER:
            nxt_start = words[i + 1]["start"] if i + 1 < n else w["end"] + 1
            set_off_after = w["w"].rstrip().endswith(",") or nxt_start - w["end"] > 0.25
            set_off_before = prev_txt.rstrip()[-1:] in ",.?!" or w["start"] - prev_end > 0.25
            if set_off_after and set_off_before:
                cuts.append({"start": w["start"], "end": w["end"], "reason": "filler", "detail": w["w"]})
            continue
        if i + 1 < n and (t, norm(words[i + 1]["w"])) in SOFT_PHRASES:
            w2 = words[i + 1]
            if w2["w"].rstrip().endswith(",") and (prev_txt.rstrip()[-1:] in ",.?!"):
                cuts.append({"start": w["start"], "end": w2["end"], "reason": "filler",
                             "detail": f'{w["w"]} {w2["w"]}'})
    return cuts


def sentences(words: list[dict]) -> list[list[dict]]:
    out, cur = [], []
    for w in words:
        if cur and w["start"] - cur[-1]["end"] > 1.0:
            out.append(cur); cur = []
        cur.append(w)
        if re.search(r"[.?!]['\"]?$", w["w"]):
            out.append(cur); cur = []
    if cur:
        out.append(cur)
    return out


def content_tokens(sent: list[dict]) -> list[str]:
    return [t for t in (norm(w["w"]) for w in sent) if t and t not in ALWAYS_FILLER]


def is_near_dup(a: list[str], b: list[str]) -> bool:
    if len(a) < 3 or len(b) < 3:
        return False
    if difflib.SequenceMatcher(None, a, b).ratio() >= 0.8:
        return True
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)   # "we open at seven" inside "come say hi we open at seven"
    m = difflib.SequenceMatcher(None, short, long_).find_longest_match(0, len(short), 0, len(long_))
    return m.size >= 3 and m.size / len(short) >= 0.85


def find_retakes(words: list[dict], window: int = 2, max_span: float = 8.0) -> list[dict]:
    sents = [s for s in sentences(words) if content_tokens(s)]
    cuts = []
    for i, s in enumerate(sents):
        a = content_tokens(s)
        for j in range(i + 1, min(i + 1 + window, len(sents))):
            later = sents[j]
            if later[0]["start"] - s[-1]["end"] > max_span:
                break
            if is_near_dup(a, content_tokens(later)):
                cuts.append({"start": s[0]["start"], "end": s[-1]["end"], "reason": "retake",
                             "detail": " ".join(w["w"] for w in s)})
                break
    return cuts


def merge(intervals: list[dict]) -> list[dict]:
    """Resolve overlaps into contiguous, non-overlapping pieces. Where cuts overlap, the higher-priority
    reason wins (retake > filler > dead-air), so every removed second carries exactly one reason."""
    pts = sorted({p for c in intervals for p in (c["start"], c["end"])})
    out: list[dict] = []
    for a, b in zip(pts, pts[1:]):
        cover = [c for c in intervals if c["start"] <= a and c["end"] >= b]
        if not cover:
            continue
        top = max(cover, key=lambda c: PRIORITY[c["reason"]])
        if out and out[-1]["reason"] == top["reason"] and abs(out[-1]["end"] - a) < 1e-6 \
                and out[-1]["detail"] == top.get("detail", ""):
            out[-1]["end"] = b
        else:
            out.append({"start": a, "end": b, "reason": top["reason"], "detail": top.get("detail", "")})
    # Absorb gaps under 20 ms between pieces (rounding noise), then drop pieces under 20 ms.
    for x, y in zip(out, out[1:]):
        if 0 < y["start"] - x["end"] < 0.02:
            x["end"] = y["start"]
    return [{**c, "start": round(c["start"], 3), "end": round(c["end"], 3)} for c in out
            if c["end"] - c["start"] >= 0.02]


def main() -> None:
    ap = argparse.ArgumentParser(description="Transcript + audio -> EDL (dead air, fillers, retakes).")
    ap.add_argument("clip")
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep-hook-seconds", type=float, default=2.0)
    ap.add_argument("--silence-db", type=float, default=-35.0)
    ap.add_argument("--min-gap", type=float, default=0.45)
    ap.add_argument("--no-fillers", action="store_true", help="keep fillers")
    ap.add_argument("--no-retakes", action="store_true", help="keep retakes")
    a = ap.parse_args()

    clip = str(Path(a.clip).resolve())
    info = video_info(clip)
    dur = info["duration"]
    tr = json.loads(Path(a.transcript).read_text())
    words = [w for w in tr.get("words", []) if w.get("end", 0) > w.get("start", 0)]
    hook = max(0.0, a.keep_hook_seconds)

    cuts: list[dict] = []
    for s, e in silences(clip, a.silence_db, a.min_gap):
        e = min(e, dur)
        if e >= dur - 0.05:                    # trailing silence: keep one breath after the last word
            cuts.append({"start": s + BREATH, "end": dur, "reason": "dead-air", "detail": f"{e - s:.2f}s tail"})
        elif s <= 0.05:                        # leading silence: keep one breath before the first word
            cuts.append({"start": 0.0, "end": e - BREATH, "reason": "dead-air", "detail": f"{e - s:.2f}s lead"})
        else:
            cuts.append({"start": s + BREATH, "end": e - BREATH, "reason": "dead-air", "detail": f"{e - s:.2f}s gap"})
    if not a.no_fillers:
        cuts += find_fillers(words)
    if not a.no_retakes:
        cuts += find_retakes(words)

    # A removed word span swallows the pause after it, up to the next word. The pause BEFORE it stays
    # as the breath, so "cafe. [um] We" plays as "cafe. We" with natural air, not a jump cut on silence.
    starts = sorted(w["start"] for w in words)
    for c in cuts:
        if c["reason"] in ("filler", "retake"):
            nxt = next((st for st in starts if st >= c["end"] - 0.01), None)
            c["end"] = max(c["end"], nxt if nxt is not None else c["end"])

    # Hook protection: nothing starts before `hook`. A word straddling the hook boundary is kept whole.
    guarded = []
    for c in cuts:
        if c["end"] <= hook:
            continue
        if c["start"] < hook:
            if c["reason"] != "dead-air":
                continue
            c = {**c, "start": hook}
        if c["end"] - c["start"] >= 0.06:
            guarded.append({**c, "start": round(c["start"], 3), "end": round(min(c["end"], dur), 3)})
    removed = merge(guarded)

    keep, t = [], 0.0
    for r in removed:
        if r["start"] - t > 0.001:
            keep.append({"start": round(t, 3), "end": round(r["start"], 3), "reason": "speech"})
        t = r["end"]
    if dur - t > 0.001:
        keep.append({"start": round(t, 3), "end": round(dur, 3), "reason": "speech"})
    # Slivers under 0.2 s are clicks, not speech; fold them into the cut on either side.
    keep = [k for k in keep if k["end"] - k["start"] >= 0.2 or k["start"] < hook]

    by = {r: round(sum(x["end"] - x["start"] for x in removed if x["reason"] == r), 3) for r in PRIORITY}
    kept = round(sum(k["end"] - k["start"] for k in keep), 3)
    edl = {
        "source": clip, "duration": dur, "hook_seconds": hook,
        "keep": keep, "removed": removed,
        "stats": {
            "duration_in": dur, "duration_out": kept, "removed_seconds": round(dur - kept, 3),
            "removed_pct": round((dur - kept) / dur * 100, 1) if dur else 0,
            "segments": len(keep),
            "count": {r: sum(1 for x in removed if x["reason"] == r) for r in PRIORITY},
            "seconds": by,
            "settings": {"silence_db": a.silence_db, "min_gap": a.min_gap, "keep_hook_seconds": hook},
        },
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(edl, indent=1))
    c = edl["stats"]["count"]
    print(f"cut {Path(clip).name}: {dur:.2f}s -> {kept:.2f}s ({edl['stats']['removed_pct']}% shorter), "
          f"{len(keep)} segments; removed {c['dead-air']} dead-air, {c['filler']} filler, "
          f"{c['retake']} retake -> {a.out}")


if __name__ == "__main__":
    main()
