#!/usr/bin/env python3
"""ReelReady render engine — apply an EDL: cut, crossfade, reframe, loudness-normalise.

    python3 engines/render_cut.py --edl edl.json --out draft.mp4 --aspect 9:16|16:9|4:5 [--fps 30]

What it does
  * Concatenates the EDL's `keep` ranges with 0.08 s video+audio crossfades.
  * Smart reframe: 9:16 -> 1080x1920, 16:9 -> 1920x1080, 4:5 -> 1080x1350. A source already at the
    target aspect is only scaled; anything else is scaled to cover and center-cropped.
  * Two-pass loudnorm to -16 LUFS integrated, -1.5 dBTP.
  * H.264 High profile, yuv420p, AAC 192 kb/s at 48 kHz, +faststart.
Also writes <out>.words.json: the transcript words re-timed onto the draft timeline (for captions),
when the EDL's sibling transcript is passed with --transcript.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True  # keep engines/ free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _media import need, run, video_info  # noqa: E402

SIZES = {"9:16": (1080, 1920), "16:9": (1920, 1080), "4:5": (1080, 1350)}
XF = 0.08


def reframe(src_w: int, src_h: int, tw: int, th: int) -> str:
    if src_w and src_h and abs(src_w / src_h - tw / th) < 0.01:
        return f"scale={tw}:{th}:flags=lanczos,setsar=1"
    return (f"scale={tw}:{th}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={tw}:{th},setsar=1")


def remap_words(words: list[dict], keep: list[dict], offsets: list[float]) -> list[dict]:
    """Re-time words onto the draft. A word belongs to the kept range it overlaps most, if that overlap
    is >= 0.1 s (Whisper often stretches a word's start back over the silence before it, so a midpoint
    test would drop audible words that sit right after a cut)."""
    out = []
    for w in words:
        best, best_ov = None, 0.0
        for k, off in zip(keep, offsets):
            ov = min(w["end"], k["end"]) - max(w["start"], k["start"])
            if ov > best_ov:
                best, best_ov = (k, off), ov
        if best and best_ov >= min(0.1, (w["end"] - w["start"]) * 0.5):
            k, off = best
            s = max(w["start"], k["start"]) - k["start"] + off
            e = min(w["end"], k["end"]) - k["start"] + off
            out.append({"w": w["w"], "start": round(s, 3), "end": round(e, 3)})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Render an EDL to a draft MP4.")
    ap.add_argument("--edl", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--aspect", default="9:16", choices=list(SIZES))
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--preset", default="medium", help="x264 preset (veryfast for quick previews)")
    ap.add_argument("--transcript", default=None, help="transcript.json to re-time onto the draft")
    a = ap.parse_args()
    need("ffmpeg")

    t0 = time.time()
    edl = json.loads(Path(a.edl).read_text())
    src = edl["source"]
    keep = [k for k in edl["keep"] if k["end"] - k["start"] > 0.01]
    if not keep:
        sys.exit("error: EDL has no keep ranges")
    info = video_info(src)
    tw, th = SIZES[a.aspect]
    vf = reframe(info["width"], info["height"], tw, th)
    has_audio = info["has_audio"]

    # One seeked input per kept range keeps memory flat however many cuts there are.
    xf = min(XF, min(k["end"] - k["start"] for k in keep) / 3)
    cmd = ["ffmpeg", "-y", "-v", "error", "-stats_period", "5"]
    for k in keep:
        cmd += ["-ss", f"{k['start']:.3f}", "-t", f"{k['end'] - k['start']:.3f}", "-i", src]
    parts, durs = [], [k["end"] - k["start"] for k in keep]
    for i in range(len(keep)):
        parts.append(f"[{i}:v]{vf},fps={a.fps},format=yuv420p,settb=AVTB,setpts=PTS-STARTPTS[v{i}]")
        if has_audio:
            parts.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[a{i}]")
    vlast, alast, acc = "v0", "a0", durs[0]
    offsets = [0.0]
    for i in range(1, len(keep)):
        off = acc - xf
        offsets.append(off)
        parts.append(f"[{vlast}][v{i}]xfade=transition=fade:duration={xf:.3f}:offset={off:.3f}[vx{i}]")
        vlast = f"vx{i}"
        if has_audio:
            parts.append(f"[{alast}][a{i}]acrossfade=d={xf:.3f}:c1=tri:c2=tri[ax{i}]")
            alast = f"ax{i}"
        acc = off + durs[i]

    with tempfile.TemporaryDirectory() as tmp:
        stage = str(Path(tmp) / "stage.mkv")
        maps = ["-map", f"[{vlast}]"] + (["-map", f"[{alast}]"] if has_audio else [])
        run(cmd + ["-filter_complex", ";".join(parts)] + maps +
            ["-c:v", "libx264", "-profile:v", "high", "-preset", a.preset, "-crf", str(a.crf),
             "-pix_fmt", "yuv420p", "-r", str(a.fps), "-c:a", "pcm_s16le", stage])

        out_cmd = ["ffmpeg", "-y", "-v", "error", "-i", stage, "-map", "0:v"]
        if has_audio:
            # Pass 1: measure. Pass 2: linear normalise to -16 LUFS / -1.5 dBTP.
            p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", stage, "-vn", "-af",
                                "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
                               capture_output=True, text=True)
            m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", p.stderr, re.S)
            ln = "loudnorm=I=-16:TP=-1.5:LRA=11"
            if m:
                j = json.loads(m.group(0))
                if j["input_i"] not in ("-inf", "inf"):
                    ln += (f":measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}"
                           f":measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
            out_cmd += ["-map", "0:a", "-af", f"{ln},aresample=48000", "-c:a", "aac", "-b:a", "192k"]
        else:
            print("warning: source has no audio track; draft will be silent", file=sys.stderr)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        run(out_cmd + ["-c:v", "copy", "-movflags", "+faststart", a.out])

    total = acc
    if a.transcript and Path(a.transcript).exists():
        tr = json.loads(Path(a.transcript).read_text())
        words = remap_words(tr.get("words", []), keep, offsets)
        wpath = str(Path(a.out).with_suffix("")) + ".words.json"
        Path(wpath).write_text(json.dumps({"source": a.out, "words": words}, indent=1, ensure_ascii=False))
    print(f"rendered {a.out}: {len(keep)} segments, {total:.2f}s, {tw}x{th}@{a.fps:g}, "
          f"{'loudnorm -16 LUFS' if has_audio else 'no audio'} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
