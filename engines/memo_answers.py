#!/usr/bin/env python3
"""ReelReady voice memo -> answers.json. Stdlib only.

    python3 engines/memo_answers.py --transcript transcript.json --out answers.json [--source memo.m4a]

Takes the transcript of a 1 to 3 minute voice memo (engines/transcribe.py output) and writes one
answer per sentence, verbatim, ids M1, M2, ...:
    [{"id": "M1", "question": "voice memo", "answer": "<sentence>", "ts": <start seconds>,
      "source": "memo.m4a"}, ...]
A sentence ends at a word that ends in . ? or !. A memo with no punctuation falls back to the
transcript segments. Nothing is reworded. The script is then built from these exactly like an
interview (engines/script_check.py checks it with the answers-only rule).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True


def sentences(d: dict) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    words = d.get("words") or []
    cur: list[str] = []
    start = 0.0
    for w in words:
        t = str(w.get("w", w.get("word", ""))).strip()
        if not t:
            continue
        if not cur:
            start = float(w.get("start", 0.0))
        cur.append(t)
        if t[-1] in ".?!":
            out.append((" ".join(cur), start))
            cur = []
    if cur:
        out.append((" ".join(cur), start))
    if len(out) <= 1 and d.get("segments"):
        out = [(str(s.get("text", "")).strip(), float(s.get("start", 0.0)))
               for s in d["segments"] if str(s.get("text", "")).strip()]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Split a voice-memo transcript into answers M1, M2, ...")
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--source", default="", help="the memo file name, noted on each answer")
    a = ap.parse_args()
    try:
        d = json.loads(Path(a.transcript).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"MEMO FAIL: cannot read transcript ({e})")
        return 1
    rows = [{"id": f"M{i}", "question": "voice memo", "answer": t, "ts": round(s, 2),
             **({"source": a.source} if a.source else {})}
            for i, (t, s) in enumerate(sentences(d), 1)]
    if not rows:
        print("MEMO FAIL: no words in the transcript")
        return 1
    Path(a.out).write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"MEMO ok: {len(rows)} sentences -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
