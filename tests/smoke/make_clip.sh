#!/usr/bin/env bash
# Make a 20 s 1080x1920 "talking head" stand-in with real speech, for the engine smoke test.
#   bash tests/smoke/make_clip.sh [out.mp4]
# Cream background, a dark circle drifting as the "subject", macOS `say -v Samantha` voice.
# The line has one filler ("Um.") and one retake ("We open at seven." said twice) to cut,
# plus a pause and a long silent tail (dead air).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/out/clip.mp4}"
mkdir -p "$(dirname "$OUT")"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

command -v say >/dev/null || { echo "make_clip.sh needs macOS 'say'"; exit 1; }
command -v ffmpeg >/dev/null || { echo "make_clip.sh needs ffmpeg"; exit 1; }

# [[slnc N]] inserts N ms of silence, so there is real dead air for silencedetect to find.
say -v Samantha -r 165 -o "$TMP/voice.aiff" \
  "[[slnc 400]] Hi, I'm, um, the owner of a small cafe. We open at seven. [[slnc 700]] Um. [[slnc 1200]] Come say hi, we open at seven. Our address is on the screen."

# A 360 px dark circle with an alpha edge, rendered once, then overlaid on a moving path.
ffmpeg -v error -y -f lavfi -i "color=c=black@0.0:s=360x360,format=rgba" -frames:v 1 \
  -vf "geq=r='38':g='34':b='32':a='if(lte(hypot(X-180,Y-180),178),255,0)'" "$TMP/circle.png"

ffmpeg -v error -y \
  -f lavfi -i "color=c=0xF3EBDD:s=1080x1920:r=30:d=20" \
  -loop 1 -framerate 30 -i "$TMP/circle.png" \
  -i "$TMP/voice.aiff" \
  -filter_complex "[0:v][1:v]overlay=x='360+140*sin(t*0.9)':y='700+60*sin(t*1.7)':shortest=1,format=yuv420p[v];[2:a]apad,atrim=0:20,aresample=48000[a]" \
  -map "[v]" -map "[a]" -t 20 -c:v libx264 -preset veryfast -crf 26 -c:a aac -b:a 128k -movflags +faststart "$OUT"

echo "made $OUT ($(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT")s)"
