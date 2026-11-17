#!/usr/bin/env bash
# Studio smoke test (no browser): sorter, undo, Studio server, review round trip.
#   bash tests/smoke/studio.sh        (run.sh calls it too)
# Builds a throwaway main folder in tests/smoke/out/studio_home with a talking clip (macOS `say`), silent
# b-roll, b-roll with room noise, a voice note, a photo, a 1 s clip and a name clash; then asserts:
# every file lands in its group, the clash is left where it was, a second sort moves nothing, --undo restores
# every path, size and mtime exactly; the Studio serves /api/library, a thumbnail, a Range request (206) and
# refuses path traversal (403); an incomplete review is refused (400), a complete one is written and
# `rr.py wait-review` prints it. Prints STUDIO PASS, exits non-zero on any failure.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/tests/smoke/out"
H="$OUT/studio_home"
PORT="${STUDIO_SMOKE_PORT:-4890}"
export REELREADY_HOME="$H" REELREADY_NO_BROWSER=1
mkdir -p "$OUT"
python3 -c 'import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)' "$H"
cd "$ROOT"
python3 scripts/init.py --path "$H" --no-pointer > /dev/null
RAW="$H/raw footage"
command -v say >/dev/null || { echo "studio.sh needs macOS 'say'"; exit 1; }

echo "== studio: make a mixed raw footage folder"
TMPD="$(mktemp -d)"
say -v Samantha -o "$TMPD/v.aiff" "Hi, I run a small bakery. Every morning we fold croissants by hand, and it takes three days."
ff() { ffmpeg -v error -y "$@"; }
ff -f lavfi -i "color=c=0xC9A27E:s=540x960:r=30:d=7" -i "$TMPD/v.aiff" -filter_complex "[1:a]apad,atrim=0:7[a]" \
   -map 0:v -map "[a]" -t 7 -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac "$RAW/talk.mov"
ff -f lavfi -i "testsrc2=s=960x540:r=30:d=4" -c:v libx264 -preset ultrafast -pix_fmt yuv420p "$RAW/shelf.mp4"
ff -f lavfi -i "testsrc2=s=540x960:r=30:d=5" -f lavfi -i "anoisesrc=c=brown:a=0.05:d=5" -t 5 \
   -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac "$RAW/oven.mov"
ff -i "$TMPD/v.aiff" -c:a aac "$RAW/memo.m4a"
ff -f lavfi -i "testsrc2=s=1200x1600" -frames:v 1 "$RAW/counter.jpg"
ff -f lavfi -i "testsrc2=s=540x960:r=30:d=1" -c:v libx264 -preset ultrafast -pix_fmt yuv420p "$RAW/blip.mp4"
mkdir -p "$RAW/B-roll"
cp "$RAW/shelf.mp4" "$RAW/B-roll/dup.mp4"    # already sorted ...
ff -f lavfi -i "testsrc2=s=960x540:r=30:d=3" -c:v libx264 -preset ultrafast -pix_fmt yuv420p "$RAW/dup.mp4"  # ... and a clash
python3 -c 'import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)' "$TMPD"

snap() { python3 - "$RAW" <<'PYEOF'
import json, sys
from pathlib import Path
d = Path(sys.argv[1])
print(json.dumps({p.relative_to(d).as_posix(): [p.stat().st_size, p.stat().st_mtime_ns]
                  for p in sorted(d.rglob("*")) if p.is_file() and p.name != ".DS_Store"}, sort_keys=True))
PYEOF
}
BEFORE="$(snap)"

echo "== studio: sort"
python3 scripts/rr.py sort --json > "$OUT/studio_sort1.json"
python3 - "$RAW" "$OUT/studio_sort1.json" <<'PYEOF'
import json, sys
from pathlib import Path
raw, res = Path(sys.argv[1]), json.load(open(sys.argv[2]))
want = {"talk.mov": "Talking to camera", "shelf.mp4": "B-roll", "oven.mov": "B-roll", "memo.m4a": "Voice notes",
        "counter.jpg": "Photos", "blip.mp4": "Too short"}
fails = [f"{n} not in {g}" for n, g in want.items() if not (raw / g / n).is_file()]
if not (raw / "dup.mp4").is_file() or not (raw / "B-roll" / "dup.mp4").is_file():
    fails.append("name clash: dup.mp4 must stay at the top and the sorted one must be untouched")
if not any(l["from"] == "raw footage/dup.mp4" for l in res["left"]):
    fails.append(f"clash not reported: {res['left']}")
if res["moved"] != 6:
    fails.append(f"moved {res['moved']}, want 6")
log = [json.loads(l) for l in (raw.parent / ".reelready/sort-log.jsonl").read_text().splitlines()]
if len(log) != 6 or not all({"batch", "ts", "from", "to", "reason"} <= set(r) for r in log):
    fails.append(f"sort-log.jsonl: {len(log)} lines")
lib = json.load(open(raw.parent / ".reelready/library.json"))
if len(lib["items"]) != 8 or not all(i["thumb"] and (raw.parent / i["thumb"]).is_file() for i in lib["items"]):
    fails.append("library.json: want 8 items, each with a thumbnail")
if fails:
    print("STUDIO FAIL sort:\n  " + "\n  ".join(fails)); sys.exit(1)
print(f"sort ok: {res['counts']} in {res['seconds']} s, clash left in place")
PYEOF

echo "== studio: sort again (moves nothing)"
python3 scripts/rr.py sort --json | python3 -c 'import json,sys; r=json.load(sys.stdin); sys.exit(0 if r["moved"]==0 else 1)' \
  || { echo "STUDIO FAIL: second sort moved files"; exit 1; }

echo "== studio: undo"
python3 scripts/rr.py sort --undo
[ "$(snap)" = "$BEFORE" ] || { echo "STUDIO FAIL: undo did not restore every path, size and mtime"; exit 1; }
echo "undo ok: raw footage identical to before the sort"
python3 scripts/rr.py sort --quiet

echo "== studio: server"
python3 studio/serve.py --no-open --no-build --port "$PORT" > "$OUT/studio_server.log" 2>&1 &
SPID=$!
trap 'kill $SPID 2>/dev/null || true' EXIT
B="http://localhost:$PORT"
for _ in $(seq 1 50); do curl -s -o /dev/null "$B/api/status" && break; sleep 0.1; done
code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
TH=$(curl -s "$B/api/library" | python3 -c 'import json,sys,urllib.parse as u; d=json.load(sys.stdin); print(u.quote(d["items"][0]["thumb"]))')
TK=$(python3 -c 'import urllib.parse as u; print(u.quote("raw footage/Talking to camera/talk.mov"))')
C_LIB=$(code "$B/api/library"); C_TH=$(code "$B/media/$TH"); C_RANGE=$(code -H 'Range: bytes=100-199' "$B/media/$TK")
C_TRAV=$(code --path-as-is "$B/media/../../../../etc/passwd"); C_ENC=$(code "$B/media/raw%20footage/..%2F..%2F..%2Fetc%2Fpasswd")
C_ENV=$(code "$B/media/.reelready/.env")
echo "library $C_LIB, thumbnail $C_TH, range $C_RANGE, traversal $C_TRAV/$C_ENC, .env $C_ENV"
[ "$C_LIB" = 200 ] && [ "$C_TH" = 200 ] && [ "$C_RANGE" = 206 ] && [ "$C_TRAV" = 403 ] && [ "$C_ENC" = 403 ] && [ "$C_ENV" = 403 ] \
  || { echo "STUDIO FAIL: server checks"; exit 1; }

echo "== studio: review round trip"
EXP=$(python3 scripts/rr.py export-dir "smoke review" | python3 -c 'import json,sys; print(json.load(sys.stdin)["slug"])')
W="$H/.reelready/work/$EXP"
cp "$RAW/Talking to camera/talk.mov" "$W/draft.mp4"
python3 - "$RAW/Talking to camera/talk.mov" "$W/edl.json" <<'PYEOF'
import json, sys
json.dump({"source": sys.argv[1], "duration": 7.0, "keep": [{"start": 0.3, "end": 3.0, "reason": "speech"},
           {"start": 3.4, "end": 6.5, "reason": "speech"}], "removed": [], "stats": {}}, open(sys.argv[2], "w"))
PYEOF
python3 scripts/rr.py review-request "$EXP" --edl "$W/edl.json" --draft "$W/draft.mp4" > /dev/null <<'JSON'
{"title": "Smoke review",
 "generated": [{"id": "hook-title", "kind": "hook", "text": "Three days for one croissant", "when": "0:00-0:02"},
               {"id": "end-card", "kind": "end_card", "text": "Open at 7", "when": "last 4 s"}],
 "hook_options": [{"id": "A", "text": "Hi, I run a small bakery.", "source": "owner"},
                  {"id": "B", "text": "Three days for one croissant", "source": "generated", "item_id": "hook-title"}],
 "caption_corrections": [], "brand_choices": ["Captions C1 in Inter, accent #FFC83D"]}
JSON
C_REV=$(code "$B/api/review/$EXP")
C_BAD=$(code -H 'Content-Type: application/json' -d '{"decisions":{"hook-title":{"action":"approve"}},"hook":"B"}' "$B/api/review/$EXP")
set +e
python3 scripts/rr.py wait-review "$EXP" --timeout 1 > /dev/null 2>&1; EARLY=$?
python3 scripts/rr.py wait-review "$EXP" --timeout 30 > "$OUT/studio_review.json" 2> "$OUT/studio_wait.err" &
WPID=$!
sleep 0.5
C_OK=$(code -H 'Content-Type: application/json' -H "Origin: $B" \
  -d '{"decisions":{"hook-title":{"action":"edit","text":"Three days, one croissant"},"end-card":{"action":"reject"}},"trims":[{"cut":1,"start":3.2,"end":6.6}],"hook":"B"}' \
  "$B/api/review/$EXP")
wait $WPID; WAITED=$?
set -e
echo "review GET $C_REV, incomplete POST $C_BAD, complete POST $C_OK, wait-review before $EARLY / after $WAITED"
[ "$C_REV" = 200 ] && [ "$C_BAD" = 400 ] && [ "$C_OK" = 200 ] && [ "$EARLY" = 2 ] && [ "$WAITED" = 0 ] \
  || { echo "STUDIO FAIL: review round trip"; cat "$OUT/studio_wait.err"; exit 1; }
python3 - "$OUT/studio_review.json" <<'PYEOF'
import json, sys
r = json.load(open(sys.argv[1]))
ok = (r["decisions"]["hook-title"] == {"action": "edit", "text": "Three days, one croissant"}
      and r["decisions"]["end-card"]["action"] == "reject" and r["trims"] == [{"cut": 1, "start": 3.2, "end": 6.6}]
      and r["hook"] == "B" and r.get("approved_at"))
if not ok:
    print(f"STUDIO FAIL: review.json content {r}"); sys.exit(1)
PYEOF
echo "STUDIO PASS"
