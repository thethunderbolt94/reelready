#!/usr/bin/env bash
# Branded overlays smoke test: the smoke clip through overlays (all four kinds) + captions (emphasis per group)
# + sound + QA + taste, for BOTH generic brand fixtures in tests/fixtures/brands/ (warm-cafe, clean-studio).
#   bash tests/smoke/overlays.sh [out_dir]          (default tests/smoke/out/overlays; needs the internet once
#                                                    for the Google Fonts download, ~3 HyperFrames renders a brand)
# Reuses tests/smoke/out/draft.mp4 + draft.words.json from run.sh when present, else makes them.
# Per brand: a throwaway main folder in <out_dir>/<brand>/home, brand_from_site.py on the fixture site (cafe),
# rr.py fonts --yes, rr.py recommend-accent, overlays.py, captions.py --emphasis group, sound.py, qa.py, taste.py
# --overlays. Also checks the taste gate FAILS an off-brand overlay sidecar.
# Prints "OVERLAYS OK" at the end; exits non-zero on any failure.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="${1:-$ROOT/tests/smoke/out/overlays}"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY=python3
E="$ROOT/engines"
FX="$ROOT/tests/fixtures/brands"
BASE="$ROOT/tests/smoke/out"
mkdir -p "$OUT"

if [ ! -f "$BASE/draft.mp4" ] || [ ! -f "$BASE/draft.words.json" ]; then
  echo "== make the smoke draft (clip -> transcribe -> cut -> render_cut)"
  mkdir -p "$BASE"
  bash "$ROOT/tests/smoke/make_clip.sh" "$BASE/clip.mp4"
  "$PY" "$E/transcribe.py" "$BASE/clip.mp4" --out "$BASE/transcript.json" 2>&1 | grep -v HF_TOKEN
  "$PY" "$E/cut.py" "$BASE/clip.mp4" --transcript "$BASE/transcript.json" --out "$BASE/edl.json"
  "$PY" "$E/render_cut.py" --edl "$BASE/edl.json" --out "$BASE/draft.mp4" --aspect 9:16 --transcript "$BASE/transcript.json"
fi

echo "== brand from a website (fixture site, offline)"
"$PY" "$ROOT/scripts/brand_from_site.py" "$FX/warm-cafe/site/index.html" --out "$OUT/site-proposal.json"
"$PY" - "$OUT/site-proposal.json" <<'PYEOF'
import json, sys
p = json.load(open(sys.argv[1]))["proposal"]
c, f = p["brand"]["colors"], p["brand"]["fonts"]
want = {"accent": "#B4502A", "background": "#FCF8F3", "text": "#2B1A11"}
bad = [f"{k} {c.get(k)} != {v}" for k, v in want.items() if c.get(k) != v]
if f.get("heading") != "Fraunces" or f.get("body") != "Inter":
    bad.append(f"fonts {f}")
if not p["logo_candidates"] or "seal" not in p["logo_candidates"][0]["url"]:
    bad.append(f"logo {p['logo_candidates'][:1]}")
if bad:
    print("BRAND FROM SITE FAILED: " + "; ".join(bad)); sys.exit(1)
print(f"BRAND FROM SITE PASS: {c}, {f['heading']} + {f['body']}, logo {p['logo_candidates'][0]['url']}")
PYEOF

for B in warm-cafe clean-studio; do
  echo "== $B"
  W="$OUT/$B"; H="$W/home"
  mkdir -p "$W"
  "$PY" - "$FX/$B" "$H" <<'PYEOF'
import shutil, sys
from pathlib import Path
src, home = Path(sys.argv[1]), Path(sys.argv[2])
for d in ("raw footage", "references", "assets", "exports", ".reelready"):
    (home / d).mkdir(parents=True, exist_ok=True)
shutil.copyfile(src / "profile.json", home / ".reelready/style-profile.json")   # throwaway copy for this run
for f in (src / "assets").glob("*") if (src / "assets").is_dir() else []:
    if f.is_file():
        shutil.copyfile(f, home / "assets" / f.name)
PYEOF
  export REELREADY_HOME="$H"
  P="$H/.reelready/style-profile.json"
  "$PY" "$ROOT/scripts/rr.py" fonts --yes --profile "$P"
  "$PY" "$ROOT/scripts/rr.py" recommend-accent --profile "$P"
  # caption flags from the profile: body bold for the words, heading italic for the emphasis word
  read -r ACCENT BODY_FILE BODY_FAM EM_FILE EM_FAM MIX <<<"$("$PY" - "$P" <<'PYEOF'
import json, sys
p = json.load(open(sys.argv[1])); b = p["brand"]; faces = b["fonts"].get("faces") or []
def face(role, style, weight):
    c = [f for f in faces if f["role"] == role and f["style"] == style]
    return min(c, key=lambda f: abs(f["weight"] - weight)) if c else None
body, em = face("body", "normal", 700), face("heading", "italic", 400)
acc = (p.get("captions") or {}).get("accent_color") or b["colors"]["accent"]
print(acc, body["file"], body["family"].replace(" ", "_"), em["file"], em["family"].replace(" ", "_"),
      ",".join(p["default_mix"]))
PYEOF
)"
  S_CARD=$(echo "$MIX" | tr ',' '\n' | grep '^S' | head -1)
  case "$S_CARD" in S2) PRESET=punchy;; S3) PRESET=cinematic;; S4) PRESET=calm;; *) PRESET=clean;; esac

  "$PY" "$E/overlays.py" "$BASE/draft.mp4" --spec "$FX/$B/overlays.json" --profile "$P" --out "$W/graphics.mp4"
  "$PY" "$E/captions.py" "$W/graphics.mp4" --words "$BASE/draft.words.json" --out "$W/captioned.mp4" \
    --accent-color "$ACCENT" --max-words 3 --font "$H/$BODY_FILE" --font-family "${BODY_FAM//_/ }" --font-weight 400 \
    --emphasis group --emphasis-font "$H/$EM_FILE" --emphasis-family "${EM_FAM//_/ }"
  "$PY" "$E/sound.py" "$W/captioned.mp4" --out "$W/final.mp4" --edl "$BASE/edl.json" \
    --captions "$BASE/draft.words.json" --preset "$PRESET"
  "$PY" "$E/qa.py" "$W/final.mp4" --frames 6 --out "$W/qa" | tee "$W/qa.txt"
  # one frame in the middle of each overlay item (qa.py's frame_hook / frame_end land on the hook and end card)
  "$PY" - "$W/graphics.overlays.json" <<'PYEOF' | while read -r KIND T; do
import json, sys
for it in json.load(open(sys.argv[1]))["items"]:
    print(it["kind"], round((it["start"] + it["end"]) / 2 + 0.15, 2))
PYEOF
    ffmpeg -v error -y -ss "$T" -i "$W/final.mp4" -frames:v 1 -vf scale=512:-2 -q:v 3 "$W/qa/frame_$KIND.jpg"
  done
  "$PY" "$E/taste.py" --profile "$P" --plan "$FX/$B/plan.md" --captions "$W/captioned.captions.json" \
    --sound "$W/final.sound.json" --overlays "$W/graphics.overlays.json" --mix "$MIX" | tee "$W/taste.txt"
  "$PY" - "$W" "$BASE" <<'PYEOF'
import json, sys
from pathlib import Path
w = Path(sys.argv[1])
o = json.load(open(w / "graphics.overlays.json")); c = json.load(open(w / "captioned.captions.json"))
fails = []
if sorted(i["kind"] for i in o["items"]) != ["end_card", "hook", "lower_third", "polaroid"]:
    fails.append(f"items {[i['kind'] for i in o['items']]}")
if not (o["checks"]["inside_safe_zone"] and o["checks"]["clear_of_captions"]):
    fails.append(f"layout checks {o['checks']}")
if c["emphasis"]["mode"] != "group" or c["emphasis"]["font_source"] != "brand" or not c["emphasis"]["words"]:
    fails.append(f"emphasis {c['emphasis']}")
words = [x["w"] for x in json.load(open(Path(sys.argv[2]) / "draft.words.json"))["words"]]
if any(e["w"] not in words for e in c["emphasis"]["words"]):
    fails.append("an emphasis word is not a spoken word")
if fails:
    print("OVERLAYS CONTRACT FAILED: " + "; ".join(fails)); sys.exit(1)
print(f"OVERLAYS CONTRACT PASS: {len(o['items'])} items, fonts "
      f"{sorted({f['family'] + ' ' + f['source'] for f in o['fonts']})}, emphasis "
      f"{[e['w'] for e in c['emphasis']['words']]}")
PYEOF
  unset REELREADY_HOME
done

echo "== taste gate must FAIL an off-brand overlay sidecar"
"$PY" - "$OUT/warm-cafe/graphics.overlays.json" "$OUT/offbrand.overlays.json" <<'PYEOF'
import json, sys
o = json.load(open(sys.argv[1]))
o["colors"]["#FFD60A"] = ["hook.title"]
o["fonts"][0].update(family="Inter", source="bundled-fallback", wanted="Fraunces")
json.dump(o, open(sys.argv[2], "w"))
PYEOF
set +e
"$PY" "$E/taste.py" --profile "$OUT/warm-cafe/home/.reelready/style-profile.json" --plan "$FX/warm-cafe/plan.md" \
  --overlays "$OUT/offbrand.overlays.json" --mix H7,C1,L5,B5,O4,S4 > "$OUT/taste_offbrand.txt"
RC=$?
set -e
if [ "$RC" -ne 1 ] || ! grep -q '^TASTE FAIL overlay-fonts' "$OUT/taste_offbrand.txt" \
   || ! grep -q '^TASTE FAIL overlay-colors' "$OUT/taste_offbrand.txt"; then
  echo "TASTE GATE DID NOT CATCH OFF-BRAND OVERLAYS"; exit 1
fi
echo "TASTE OVERLAY RULES PASS: off-brand fonts and colours fail"
echo "OVERLAYS OK"
