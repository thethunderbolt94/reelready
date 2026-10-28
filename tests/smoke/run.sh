#!/usr/bin/env bash
# Engine smoke test: make clip -> transcribe (whisper-local) -> cut -> render_cut -> qa.
#   bash tests/smoke/run.sh
# Asserts: QA passes, the retake ("We open at seven." said twice) and the standalone "Um." were cut,
# and re-transcribing the draft hears "open at seven" exactly once; then captions.py + QA on the result.
# Exits non-zero on any failure, including the captions step ("CAPTIONS SKIPPED: <reason>").
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/tests/smoke/out"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY=python3
E="$ROOT/engines"
mkdir -p "$OUT"

stamp() { python3 -c 'import time;print(time.time())'; }
lap() { python3 -c "print(f'{$(stamp)-$1:.1f}')"; }

echo "== make clip"
bash "$ROOT/tests/smoke/make_clip.sh" "$OUT/clip.mp4"

echo "== transcribe (whisper-local)"
t=$(stamp); "$PY" "$E/transcribe.py" "$OUT/clip.mp4" --out "$OUT/transcript.json" 2>&1 | grep -v HF_TOKEN; T_TR=$(lap "$t")

echo "== cut"
t=$(stamp); "$PY" "$E/cut.py" "$OUT/clip.mp4" --transcript "$OUT/transcript.json" --out "$OUT/edl.json"; T_CUT=$(lap "$t")

echo "== render_cut"
t=$(stamp); "$PY" "$E/render_cut.py" --edl "$OUT/edl.json" --out "$OUT/draft.mp4" --aspect 9:16 \
  --transcript "$OUT/transcript.json"; T_RENDER=$(lap "$t")

echo "== qa"
"$PY" "$E/qa.py" "$OUT/draft.mp4" --frames 6 --out "$OUT/qa_draft" | tee "$OUT/qa_draft.txt"

echo "== verify cuts (re-transcribe the draft)"
"$PY" "$E/transcribe.py" "$OUT/draft.mp4" --out "$OUT/draft_transcript.json" 2>&1 | grep -v HF_TOKEN

"$PY" - "$OUT" <<'PYEOF'
import json, re, sys
out = sys.argv[1]
edl = json.load(open(f"{out}/edl.json"))
qa = json.load(open(f"{out}/qa_draft/probe.json"))
heard = " ".join(w["w"] for w in json.load(open(f"{out}/draft_transcript.json"))["words"]).lower()
flat = re.sub(r"[^a-z ]", "", heard)
fails = []
if not qa["pass"]:
    fails.append(f"qa failed: {qa['fails']}")
retakes = [r for r in edl["removed"] if r["reason"] == "retake"]
if not any("open at seven" in r["detail"].lower() for r in retakes):
    fails.append(f"retake not in EDL: {retakes}")
fillers = [r for r in edl["removed"] if r["reason"] == "filler"]
if not any(r["start"] >= edl["hook_seconds"] for r in fillers):
    fails.append(f"no filler cut after the hook: {fillers}")
if flat.count("open at seven") != 1:
    fails.append(f"draft says 'open at seven' {flat.count('open at seven')}x (want 1): {heard!r}")
if flat.split().count("um") > 1:   # the one inside the 2 s hook is protected by design
    fails.append(f"draft still has {flat.split().count('um')} ums: {heard!r}")
print(f"draft hears: {heard}")
if fails:
    print("SMOKE FAIL:\n  " + "\n  ".join(fails)); sys.exit(1)
s = edl["stats"]
print(f"SMOKE PASS: {s['duration_in']}s -> {s['duration_out']}s, removed {s['count']}")
PYEOF

echo "== captions (HyperFrames burn-in: white bold sans, one yellow accent word)"
rm -f "$OUT/captioned.mp4" "$OUT/qa_captioned.txt"   # never let a stale file from an earlier run pass QA
t=$(stamp)
if ! "$PY" "$E/captions.py" "$OUT/draft.mp4" --words "$OUT/draft.words.json" --out "$OUT/captioned.mp4" \
     --accent seven 2> "$OUT/captions_err.txt"; then
  REASON=$(grep -v '^[[:space:]]*$' "$OUT/captions_err.txt" | head -1 | sed 's/^error: //')
  echo "CAPTIONS SKIPPED: ${REASON:-captions.py failed (see tests/smoke/out/captions_err.txt)}"
  echo "SMOKE FAIL: cut/render/qa passed, captions did not"
  exit 1
fi
T_CAP=$(lap "$t")
"$PY" "$E/qa.py" "$OUT/captioned.mp4" --frames 6 --out "$OUT/qa_captioned" | tee "$OUT/qa_captioned.txt"

echo "timings: transcribe ${T_TR}s, cut ${T_CUT}s, render ${T_RENDER}s, captions ${T_CAP}s" | tee "$OUT/timings.txt"
echo "SMOKE OK"
