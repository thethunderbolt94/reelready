#!/usr/bin/env python3
"""ReelReady caption burn-in — verbatim, word-timed captions rendered with HyperFrames.

    python3 engines/captions.py <draft.mp4> --words <draft.words.json> --out captioned.mp4
        [--accent seven] [--accent-color #FFD60A] [--max-words 3] [--keep-project <dir>]

* Words come straight from the transcript (re-timed onto the draft by render_cut.py). Nothing is
  rewritten. Pure fillers (um, uh, er...) are dropped from the caption track only, as in the
  embedded-captions skill's "drop" class; the audio is untouched.
* Style: white heavy sans (bundled Inter 700), dark stroke for legibility on any background,
  2-3 word groups in the lower-middle safe zone, each word pops in on its own timestamp.
  Exactly one accent word (first match of --accent, else the longest content word) is yellow.
* Rendering: builds a tiny HyperFrames project and runs the pinned CLI via npx (Chrome headless,
  local, no key). The draft's audio is muxed back untouched, so loudness stays at -16 LUFS.
For richer looks (behind-the-subject hero words, 35 identities) use .claude/skills/embedded-captions.
"""
from __future__ import annotations

import argparse
import atexit
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True  # keep engines/ free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _media import need, run, video_info  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HF_VERSION = os.environ.get("REELREADY_HYPERFRAMES_VERSION", "0.8.143")
FILLERS = {"um", "umm", "uh", "uhh", "uhm", "er", "erm", "ah", "hmm", "mm"}
STOP = {"the", "a", "an", "and", "or", "but", "so", "of", "to", "in", "on", "at", "is", "are", "we",
        "i", "i'm", "you", "it", "our", "my", "your", "this", "that", "with", "for", "be", "say"}


def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9']", "", w.lower())


def group(words: list[dict], max_words: int) -> list[list[dict]]:
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words or w["start"] - cur[-1]["end"] > 0.35):
            groups.append(cur); cur = []
        cur.append(w)
        if re.search(r"[.?!,;:]$", w["w"]):
            groups.append(cur); cur = []
    if cur:
        groups.append(cur)
    return groups


def build_html(words: list[dict], dur: float, w: int, h: int, accent_idx: int, accent_color: str,
               max_words: int, font_ok: bool, gsap_src: str) -> str:
    groups = group(words, max_words)
    blocks, tweens, idx = [], [], 0
    for gi, g in enumerate(groups):
        start = g[0]["start"]
        nxt = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else dur
        end = min(nxt, g[-1]["end"] + 0.6, dur)
        spans = []
        for wd in g:
            cls = "w accent" if idx == accent_idx else "w"
            spans.append(f'<span id="w{idx}" class="{cls}">{html.escape(wd["w"])}</span>')
            tweens.append(f'tl.fromTo("#w{idx}",{{opacity:0,y:18,scale:0.86}},'
                          f'{{opacity:1,y:0,scale:1,duration:0.14,ease:"back.out(2.2)"}},{wd["start"]:.3f});')
            if idx == accent_idx:
                tweens.append(f'tl.fromTo("#w{idx}",{{scale:1}},{{scale:1.14,duration:0.12,yoyo:true,repeat:1,'
                              f'ease:"power2.out"}},{wd["start"] + 0.14:.3f});')
            idx += 1
        blocks.append(f'<div class="clip cap" data-start="{start:.3f}" data-duration="{max(0.1, end - start):.3f}" '
                      f'data-track-index="1">{" ".join(spans)}</div>')
    font_face = ('@font-face{font-family:"CapSans";src:url("Inter-700-latin.woff2") format("woff2");'
                 'font-weight:700 900;}') if font_ok else ""
    fs = round(w * 0.083)              # ~90 px on a 1080-wide frame
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={w}, height={h}" />
<title>ReelReady captions</title>
<script src="{gsap_src}"></script>
<style>
{font_face}
body {{ margin:0; background:#000; }}
#root {{ position:relative; width:{w}px; height:{h}px; overflow:hidden; }}
#a-roll {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }}
.cap {{ position:absolute; left:6%; right:6%; top:{int(h * 0.60)}px; text-align:center;
  font-family:"CapSans","Inter","Helvetica Neue",Arial,sans-serif; font-weight:800; font-size:{fs}px;
  line-height:1.08; letter-spacing:-0.01em; color:#fff; }}
.w {{ display:inline-block; opacity:0; -webkit-text-stroke:{max(6, fs // 9)}px #121212; paint-order:stroke fill;
  text-shadow:0 6px 18px rgba(0,0,0,.45); }}
.w.accent {{ color:{accent_color}; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-width="{w}" data-height="{h}" data-duration="{dur:.3f}">
  <video id="a-roll" class="clip" src="draft.mp4" muted playsinline data-start="0" data-duration="{dur:.3f}" data-track-index="0"></video>
  {chr(10).join("  " + b for b in blocks)}
</div>
<script>
const tl = gsap.timeline({{ paused: true }});
{chr(10).join(tweens)}
tl.set({{}}, {{}}, {dur:.3f});
window.__timelines["main"] = tl;
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description="Burn verbatim word-level captions with HyperFrames.")
    ap.add_argument("video")
    ap.add_argument("--words", required=True, help="words json ({'words':[{w,start,end}]}) on the video's timeline")
    ap.add_argument("--out", required=True)
    ap.add_argument("--accent", default=None, help="word to highlight (first occurrence)")
    ap.add_argument("--accent-color", default="#FFD60A")
    ap.add_argument("--max-words", type=int, default=3)
    ap.add_argument("--keep-project", default=None, help="keep the HyperFrames project in this dir")
    a = ap.parse_args()
    need("ffmpeg"); need("npx")

    t0 = time.time()
    info = video_info(a.video)
    dur, w, h = info["duration"], info["width"], info["height"]
    words = [x for x in json.loads(Path(a.words).read_text())["words"] if norm(x["w"]) not in FILLERS]
    if not words:
        sys.exit("error: no words to caption")
    if a.accent:
        cand = [i for i, x in enumerate(words) if norm(x["w"]) == norm(a.accent)]
        accent_idx = cand[0] if cand else -1
    else:
        content = [(len(norm(x["w"])), i) for i, x in enumerate(words) if norm(x["w"]) not in STOP]
        accent_idx = max(content)[1] if content else -1

    proj = Path(a.keep_project) if a.keep_project else Path(tempfile.mkdtemp(prefix="rr-captions-"))
    proj.mkdir(parents=True, exist_ok=True)
    if not a.keep_project:
        atexit.register(shutil.rmtree, proj, True)   # temp project is removed on success AND on failure
    shutil.copyfile(a.video, proj / "draft.mp4")
    assets = ROOT / ".claude/skills/talking-head-recut/assets"
    font_ok = (assets / "fonts/Inter-700-latin.woff2").exists()
    if font_ok:
        shutil.copyfile(assets / "fonts/Inter-700-latin.woff2", proj / "Inter-700-latin.woff2")
    gsap_src = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"
    if (assets / "vendor/gsap.min.js").exists():
        shutil.copyfile(assets / "vendor/gsap.min.js", proj / "gsap.min.js")
        gsap_src = "gsap.min.js"
    (proj / "index.html").write_text(build_html(words, dur, w, h, accent_idx, a.accent_color, a.max_words,
                                                font_ok, gsap_src))

    env = {**os.environ, "HYPERFRAMES_SKIP_SKILLS": "1", "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
    silent = proj / "captioned_silent.mp4"
    fps = str(int(round(info["fps"] or 30)))
    p = subprocess.run(["npx", "--yes", f"hyperframes@{HF_VERSION}", "render", str(proj), "-o", str(silent),
                        "--fps", fps, "--quality", "delivery", "--quiet"], env=env, capture_output=True, text=True)
    if p.returncode != 0 or not silent.exists():
        msg = (p.stderr or "") + (p.stdout or "")
        if "Low disk space" in msg:
            sys.exit("error: HyperFrames refused to render: the disk is almost full (it needs at least 1 GB free "
                     "for temp frames). Free some space and run this again.")
        sys.exit(f"error: hyperframes render failed:\n{msg[-1500:]}")
    # Keep the draft's (already loudness-normalised) audio bit-exact; re-encode video to the delivery spec.
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-i", a.video, "-map", "0:v:0"]
    if info["has_audio"]:
        cmd += ["-map", "1:a:0", "-c:a", "copy"]
    run(cmd + ["-c:v", "libx264", "-profile:v", "high", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p",
               "-t", f"{dur:.3f}", "-movflags", "+faststart", a.out])
    acc = words[accent_idx]["w"] if accent_idx >= 0 else "none"
    print(f"captioned {a.out}: {len(words)} words, accent '{acc}', {w}x{h}, via hyperframes@{HF_VERSION} "
          f"in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
