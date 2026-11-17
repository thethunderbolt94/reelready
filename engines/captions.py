#!/usr/bin/env python3
"""ReelReady caption burn-in — verbatim, word-timed captions rendered with HyperFrames.

    python3 engines/captions.py <draft.mp4> --words <draft.words.json> --out captioned.mp4
        [--accent seven] [--accent-color #FFD60A] [--max-words 3] [--keep-project <dir>]
        [--font <brand.ttf|otf|woff|woff2>] [--font-family "Brand Name"] [--font-weight 800]
        [--font-size 90] [--emphasis group --emphasis-font <heading-italic.ttf> --emphasis-family "Name"
         [--emphasis-style italic] [--emphasis-weight 400] [--emphasis-words words.txt]]

* Words come straight from the transcript (re-timed onto the draft by render_cut.py). Nothing is
  rewritten. Pure fillers (um, uh, er...) are dropped from the caption track only, as in the
  embedded-captions skill's "drop" class; the audio is untouched.
* Style: white heavy sans (bundled Inter 700, or the owner's brand font via --font, Inter as the
  fallback), dark stroke for legibility on any background,
  2-3 word groups in the lower-middle safe zone, each word pops in on its own timestamp.
  Size: --font-size px (default 8.3% of the frame width, ~90 px at 1080 wide).
  Exactly one accent word (first match of --accent, else the longest content word) is yellow.
  --emphasis group (opt-in brand look): instead, one word per caption group is set in a second face (e.g. the
  heading's italic) in the accent colour, chosen deterministically (the group's longest content word, or the
  first word of the group found in --emphasis-words). Styling only: every word stays exactly as spoken.
* Rendering: builds a tiny HyperFrames project and runs the pinned CLI via npx (Chrome headless,
  local, no key). The draft's audio is muxed back untouched, so loudness stays at -16 LUFS.
* Writes <out stem>.captions.json (font_family, font_source, font_path, font_size, accent_color,
  accent_word, max_words, groups, words, emphasis {mode, chooser, font_family, font_source, words...}):
  the contract the taste gate reads.
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
# Font file magic -> (CSS format(), extension). Detected from the bytes, not trusted from the name.
FONT_MAGIC = [(b"wOF2", "woff2", ".woff2"), (b"wOFF", "woff", ".woff"), (b"OTTO", "opentype", ".otf"),
              (b"\x00\x01\x00\x00", "truetype", ".ttf"), (b"true", "truetype", ".ttf")]
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


def main_folder() -> Path | None:
    env = os.environ.get("REELREADY_HOME")
    if env:
        return Path(env).expanduser()
    try:
        return Path(json.loads((ROOT / ".reelready/home.json").read_text())["main_folder"]).expanduser()
    except Exception:
        return None


def resolve_font(arg: str, family: str | None) -> dict | None:
    """Find and sniff a brand font. Returns {path, family, fmt, ext} or None (after one warning line)."""
    p = Path(arg).expanduser()
    cands = [p]
    home = main_folder()
    if not p.is_absolute() and home:
        cands += [home / p, home / "assets" / p]
    for c in cands:
        try:
            with open(c, "rb") as f:
                head = f.read(4)
        except OSError:
            head = b""
        for magic, fmt, ext in FONT_MAGIC:
            if head == magic:
                fam = re.sub(r'[\x00-\x1f"\\<>;{}]', "", family or c.stem).strip() or "BrandFont"
                return {"path": c.resolve(), "family": fam, "fmt": fmt, "ext": ext}
    print(f"warning: font not found: {arg}; using Inter", file=sys.stderr)
    return None


def default_size(w: int) -> int:
    return round(w * 0.083)            # ~90 px on a 1080-wide frame


def pick_emphasis(words: list[dict], max_words: int, wanted: set[str] | None) -> list[int]:
    """One emphasis word per caption group (global word indices). Deterministic: the first word of the group
    that is in `wanted` (the --emphasis-words list), else, with no list, the group's longest content word
    (3+ letters, not a stopword; ties -> the earlier word). A group with no candidate gets none."""
    out, base = [], 0
    for g in group(words, max_words):
        best = None
        for i, wd in enumerate(g):
            n = norm(wd["w"])
            if wanted is not None:
                if n in wanted:
                    best = (0, i)
                    break
            elif len(n) >= 3 and n not in STOP and (best is None or len(n) > best[0]):
                best = (len(n), i)
        if best is not None:
            out.append(base + best[1])
        base += len(g)
    return out


def build_html(words: list[dict], dur: float, w: int, h: int, accent_idx: int, accent_color: str,
               max_words: int, font_ok: bool, gsap_src: str, brand: dict | None = None,
               weight: int = 800, size: int | None = None, emph: dict | None = None) -> str:
    """emph (group mode): {"idx": [word indices], "family": css family or None, "style", "weight",
    "face": @font-face css or ""}. Emphasis words take the accent colour and the second face; no pulse."""
    groups = group(words, max_words)
    emph_idx = set(emph["idx"]) if emph else set()
    blocks, tweens, idx = [], [], 0
    for gi, g in enumerate(groups):
        start = g[0]["start"]
        nxt = groups[gi + 1][0]["start"] if gi + 1 < len(groups) else dur
        end = min(nxt, g[-1]["end"] + 0.6, dur)
        spans = []
        for wd in g:
            cls = "w em" if idx in emph_idx else ("w accent" if idx == accent_idx and not emph else "w")
            spans.append(f'<span id="w{idx}" class="{cls}">{html.escape(wd["w"])}</span>')
            tweens.append(f'tl.fromTo("#w{idx}",{{opacity:0,y:18,scale:0.86}},'
                          f'{{opacity:1,y:0,scale:1,duration:0.14,ease:"back.out(2.2)"}},{wd["start"]:.3f});')
            if idx == accent_idx and not emph:
                tweens.append(f'tl.fromTo("#w{idx}",{{scale:1}},{{scale:1.14,duration:0.12,yoyo:true,repeat:1,'
                              f'ease:"power2.out"}},{wd["start"] + 0.14:.3f});')
            idx += 1
        blocks.append(f'<div class="clip cap" data-start="{start:.3f}" data-duration="{max(0.1, end - start):.3f}" '
                      f'data-track-index="1">{" ".join(spans)}</div>')
    font_face = ('@font-face{font-family:"CapSans";src:url("Inter-700-latin.woff2") format("woff2");'
                 'font-weight:700 900;}') if font_ok else ""
    family = '"CapSans","Inter","Helvetica Neue",Arial,sans-serif'
    if brand:   # no weight range on purpose: a regular-only file gets synthesized bold at weight 800
        font_face = (f'@font-face{{font-family:"{brand["family"]}";src:url("brand-font{brand["ext"]}") '
                     f'format("{brand["fmt"]}");}}\n' + font_face)
        family = f'"{brand["family"]}",' + family
    fs = size or default_size(w)
    em_css = ""
    if emph:
        font_face = emph["face"] + font_face
        fam = f'"{emph["family"]}",' + family if emph["family"] else family
        em_css = (f'.w.em {{ color:{accent_color}; font-family:{fam}; font-style:{emph["style"]}; '
                  f'font-weight:{emph["weight"]}; font-size:1.08em; letter-spacing:0; }}')
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
  font-family:{family}; font-weight:{weight}; font-size:{fs}px;
  line-height:1.08; letter-spacing:-0.01em; color:#fff; }}
.w {{ display:inline-block; opacity:0; -webkit-text-stroke:{max(6, fs // 9)}px #121212; paint-order:stroke fill;
  text-shadow:0 6px 18px rgba(0,0,0,.45); }}
.w.accent {{ color:{accent_color}; }}
{em_css}
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
    ap.add_argument("--font", default=None,
                    help="brand font file (ttf/otf/woff/woff2), absolute or relative to the main folder or its assets/")
    ap.add_argument("--font-family", default=None, help="CSS family name for --font (default: the file stem)")
    ap.add_argument("--font-weight", type=int, default=800, help="caption font-weight (default 800)")
    ap.add_argument("--font-size", type=int, default=None,
                    help="caption size in px on the output frame (default 8.3%% of the width, ~90 at 1080 wide)")
    ap.add_argument("--emphasis", choices=("single", "group"), default="single",
                    help="single (default): one accent word in the whole reel; group: one emphasis word per "
                         "caption group, in the accent colour and a second face (--emphasis-font)")
    ap.add_argument("--emphasis-font", default=None,
                    help="group mode: font file for emphasis words, e.g. the heading italic (ttf/otf/woff/woff2)")
    ap.add_argument("--emphasis-family", default=None, help="CSS family name for --emphasis-font")
    ap.add_argument("--emphasis-style", choices=("italic", "normal"), default="italic")
    ap.add_argument("--emphasis-weight", type=int, default=400)
    ap.add_argument("--emphasis-words", default=None,
                    help="group mode: text file of words to emphasise (one per line or comma-separated); "
                         "only these are used, at most one per group")
    a = ap.parse_args()
    if a.font_size is not None and not 24 <= a.font_size <= 400:
        sys.exit("error: --font-size must be between 24 and 400 px")
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
    brand = resolve_font(a.font, a.font_family) if a.font else None
    if brand:
        try:
            shutil.copyfile(brand["path"], proj / f"brand-font{brand['ext']}")
        except OSError:
            print(f"warning: font not found: {a.font}; using Inter", file=sys.stderr)
            brand = None
    emph, emph_meta = None, None
    if a.emphasis == "group":
        wanted = None
        if a.emphasis_words:
            try:
                raw = Path(a.emphasis_words).read_text(encoding="utf-8")
            except OSError:
                sys.exit(f"error: --emphasis-words file not found: {a.emphasis_words}")
            wanted = {norm(x) for x in re.split(r"[\n,]+", raw) if norm(x)}
        idx = pick_emphasis(words, a.max_words, wanted)
        ef = resolve_font(a.emphasis_font, a.emphasis_family) if a.emphasis_font else None
        face, efam, esrc, epath = "", None, "caption-face", None
        if ef:
            try:
                shutil.copyfile(ef["path"], proj / f"emph-font{ef['ext']}")
                face = (f'@font-face{{font-family:"{ef["family"]}";src:url("emph-font{ef["ext"]}") '
                        f'format("{ef["fmt"]}");font-style:{a.emphasis_style};font-weight:{a.emphasis_weight};}}\n')
                efam, esrc, epath = ef["family"], "brand", str(ef["path"])
            except OSError:
                print(f"warning: font not found: {a.emphasis_font}; emphasis uses the caption face", file=sys.stderr)
        emph = {"idx": idx, "family": efam, "style": a.emphasis_style, "weight": a.emphasis_weight, "face": face}
        emph_meta = {"mode": "group", "chooser": "list" if wanted is not None else "longest-content-word",
                     "font_family": efam, "font_source": esrc, "font_path": epath, "style": a.emphasis_style,
                     "weight": a.emphasis_weight, "color": a.accent_color,
                     "words": [{"i": i, "w": words[i]["w"], "start": words[i]["start"]} for i in idx]}
    gsap_src = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"
    if (assets / "vendor/gsap.min.js").exists():
        shutil.copyfile(assets / "vendor/gsap.min.js", proj / "gsap.min.js")
        gsap_src = "gsap.min.js"
    (proj / "index.html").write_text(build_html(words, dur, w, h, accent_idx, a.accent_color, a.max_words,
                                                font_ok, gsap_src, brand, a.font_weight, a.font_size, emph))

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
    if emph:
        accent_idx = -1   # group mode replaces the single accent word
    acc = words[accent_idx]["w"] if accent_idx >= 0 else "none"
    if emph_meta:
        acc = f"{len(emph_meta['words'])} emphasis words ({emph_meta['font_family'] or 'caption face'} " \
              f"{emph_meta['style']})"
    if brand:
        src, fam, fpath = "brand", brand["family"], str(brand["path"])
    elif font_ok:
        src, fam, fpath = "bundled-inter", "Inter", str(assets / "fonts/Inter-700-latin.woff2")
    else:
        src, fam, fpath = "system-fallback", "sans-serif", None
    Path(a.out).with_suffix(".captions.json").write_text(json.dumps({
        "font_family": fam, "font_source": src, "font_path": fpath, "font_size": a.font_size or default_size(w),
        "accent_color": a.accent_color,
        "accent_word": words[accent_idx]["w"] if accent_idx >= 0 else None, "max_words": a.max_words,
        "groups": len(group(words, a.max_words)), "words": len(words),
        "emphasis": emph_meta or {"mode": "single"}}, indent=2) + "\n")
    print(f"captioned {a.out}: {len(words)} words, accent '{acc}', font {fam} ({src}), {w}x{h}, "
          f"via hyperframes@{HF_VERSION} "
          f"in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
