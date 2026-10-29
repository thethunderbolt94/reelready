#!/usr/bin/env python3
"""ReelReady story engine — reorder what the owner said, never rewrite it.

    python3 engines/story.py --edl edl.json --transcript transcript.json --out edl.story.json \
        --order 3,0,1,2 [--drop 4,5] [--list]

Splits the EDL's `keep` segments at sentence boundaries (the transcript's segments), then
emits a new EDL whose `keep` list is in the order you asked for. render_cut.py plays `keep`
in list order, so the draft follows the story order. Audio and words are untouched: the
only thing this engine can do is choose which sentences play and in what order.

  --list     print the numbered sentences and exit (use this first, then pick an order)
  --order    comma-separated sentence numbers, first to last. Sentences not listed are dropped.
  --drop     sentences to drop even if --order is omitted (keeps the rest in original order)
  --min-len  drop any resulting piece shorter than this many seconds (default 0.35)

Rules the agent must follow (see .claude/skills/reelready-edit/references/story.md):
  * the hook sentence goes first and is usually the most specific line, not the greeting
  * reorder across sentence boundaries only; never cut inside a sentence
  * a sentence that depends on a previous one ("that's why...") travels with it
"""
from __future__ import annotations

import argparse
import json
import sys

sys.dont_write_bytecode = True

MIN_LEN = 0.35
PAD = 0.08  # seconds of breath kept on each side of a sentence (matches cut.py's feel)


def sentences(transcript: dict) -> list[dict]:
    segs = transcript.get("segments") or []
    out = []
    for i, s in enumerate(segs):
        text = (s.get("text") or "").strip()
        if not text:
            continue
        out.append({"n": len(out), "start": float(s["start"]), "end": float(s["end"]), "text": text})
    return out


def clip_to_keep(sent: dict, keep: list[dict], min_len: float) -> list[dict]:
    """Intersect one sentence with the kept ranges (so fillers/retakes cut earlier stay cut)."""
    pieces = []
    a0, b0 = sent["start"] - PAD, sent["end"] + PAD
    for k in keep:
        a, b = max(a0, k["start"]), min(b0, k["end"])
        if b - a >= min_len:
            pieces.append({"start": round(a, 3), "end": round(b, 3), "reason": "speech",
                           "sentence": sent["n"], "text": sent["text"]})
    return pieces


def main() -> None:
    ap = argparse.ArgumentParser(description="Reorder sentences in an EDL (story pass).")
    ap.add_argument("--edl", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out")
    ap.add_argument("--order", help="comma-separated sentence numbers, first to last")
    ap.add_argument("--drop", default="", help="comma-separated sentence numbers to drop")
    ap.add_argument("--list", action="store_true", help="print numbered sentences and exit")
    ap.add_argument("--min-len", type=float, default=MIN_LEN)
    a = ap.parse_args()

    edl = json.load(open(a.edl))
    tr = json.load(open(a.transcript))
    sents = sentences(tr)
    if not sents:
        sys.exit("error: transcript has no segments")

    if a.list or not (a.order or a.drop):
        for s in sents:
            print(f"{s['n']:>2}  [{s['start']:6.2f}-{s['end']:6.2f}]  {s['text']}")
        if not (a.order or a.drop):
            return

    drop = {int(x) for x in a.drop.split(",") if x.strip()}
    if a.order:
        order = [int(x) for x in a.order.split(",") if x.strip()]
    else:
        order = [s["n"] for s in sents if s["n"] not in drop]
    bad = [n for n in order if n < 0 or n >= len(sents)]
    if bad:
        sys.exit(f"error: unknown sentence number(s) {bad}; run with --list")
    if len(set(order)) != len(order):
        sys.exit("error: a sentence appears twice in --order")
    order = [n for n in order if n not in drop]

    keep_in = [k for k in edl["keep"] if k["end"] - k["start"] > 0.01]
    keep_out, dropped = [], []
    for n in order:
        pieces = clip_to_keep(sents[n], keep_in, a.min_len)
        if not pieces:
            dropped.append(n)
        keep_out.extend(pieces)
    if not keep_out:
        sys.exit("error: nothing left to keep")

    out = dict(edl)
    out["keep"] = keep_out
    out["story"] = {"order": order, "dropped_empty": dropped,
                    "sentences": [{"n": s["n"], "text": s["text"]} for s in sents]}
    out["kept_seconds"] = round(sum(k["end"] - k["start"] for k in keep_out), 3)
    out_path = a.out or a.edl.replace(".json", ".story.json")
    json.dump(out, open(out_path, "w"), indent=1)
    moved = sum(1 for i, n in enumerate(order) if i != n)
    print(f"story: {len(order)} of {len(sents)} sentences kept, {moved} moved, "
          f"{out['kept_seconds']:.2f}s -> {out_path}")


if __name__ == "__main__":
    main()
