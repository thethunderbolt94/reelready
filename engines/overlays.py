#!/usr/bin/env python3
"""ReelReady branded overlays: hook card, note-card lower third, polaroid beat, end card, in the owner's brand.

    python3 engines/overlays.py <video> --spec overlays.json --profile style-profile.json --out graphics.mp4
        [--home <main folder>] [--caption-band 1133:1402] [--keep-project <dir>] [--no-render]

Runs BEFORE captions.py (captions go on top), after the cut/b-roll. Renders one HyperFrames composition with the
video as the base layer, muxes the input's audio back bit-exact, and writes <out stem>.overlays.json.

Spec (times in seconds on the video's timeline; a negative start/end counts from the end; items may not overlap):
  {"items": [
    {"kind": "hook", "start": 0, "end": 2.4, "title": "Slow coffee,", "italic": "made by hand.", "on": "card|light"},
    {"kind": "lower_third", "start": 2.6, "end": 5.5, "name": "Linen & Ember", "detail": "Small cafe, Anytown"},
    {"kind": "polaroid", "start": 6, "end": 8.5, "caption": "come say hi", "bg": "blur|brand",
     "src": "<optional b-roll file>", "src_start": 0},
    {"kind": "end_card", "start": -3.5, "address": "...", "website": "...", "cta": "Visit us",
     "name": "<optional; default business.name>", "on": "light|dark"}]}
The engine renders text EXACTLY as given (it never writes or changes copy; the plan flags generated lines).
A line too long for its slot is an error, never clipped or shrunk past readability.

Brand tokens come from the profile: brand.colors (+ brand.palette) for every fill and text colour, brand.fonts
for faces (heading = display, its italic = the emphasis phrase, body = small text, hand = polaroid caption, else
the heading italic), brand.logo for the end card (else the business name in the display face).
Fonts, in order: the profile's downloaded files (brand.fonts.faces / files), else Google Fonts by name (fetched
into the scratch project, never into assets/), else the bundled Inter/Caveat fallback; the sidecar records which.

Layout (1080x1920; other 9:16 sizes scale): nothing in the top 220 px or bottom 320 px, nothing in the right
140 px of the lower half (the Instagram button rail), and no text box inside the caption band (default 59-73 %
of the height, where captions.py draws). Motion is eased (power3/sine), never linear.

Sidecar <out stem>.overlays.json: fonts [{role, family, style, weight, source, file}], colors {hex: [uses]},
items [{kind, start, end, box [x, y, w, h], text}], caption_band, checks {inside_safe_zone, clear_of_captions}.
The taste gate (taste.py --overlays) fails it when the fonts are not the brand's or a colour is off-palette.
"""
from __future__ import annotations

import argparse
import atexit
import html
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True  # keep engines/ free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _color  # noqa: E402
from _media import need, run, video_info  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HF_VERSION = os.environ.get("REELREADY_HYPERFRAMES_VERSION", "0.8.143")
ASSETS = ROOT / ".claude/skills/talking-head-recut/assets"
BUNDLED = {"Inter": {400: "Inter-400-latin.woff2", 700: "Inter-700-latin.woff2"},
           "Caveat": {400: "Caveat-400-latin.woff2", 700: "Caveat-700-latin.woff2"}}
KINDS = ("hook", "lower_third", "polaroid", "end_card")
SAFE_TOP, SAFE_BOTTOM, RAIL = 220, 320, 140          # px at 1080x1920
# Longest line each slot takes at its smallest size (chars). Longer = error: shorten it in the plan.
LIMITS = {("hook", "title"): 20, ("hook", "italic"): 22, ("lower_third", "name"): 20,
          ("lower_third", "detail"): 22, ("end_card", "name"): 18, ("end_card", "address"): 23,
          ("end_card", "website"): 23, ("end_card", "cta"): 16, ("polaroid", "caption"): 18}


def main_folder(arg: str | None, profile: Path) -> Path | None:
    if arg:
        return Path(arg).expanduser()
    if os.environ.get("REELREADY_HOME"):
        return Path(os.environ["REELREADY_HOME"]).expanduser()
    guess = profile.resolve().parent.parent
    if (guess / "assets").exists():
        return guess
    try:
        return Path(json.loads((ROOT / ".reelready/home.json").read_text(encoding="utf-8"))["main_folder"]).expanduser()
    except (OSError, ValueError, KeyError):
        return None


# ---------------------------------------------------------------- colours
class Palette:
    """Brand colours only. Every colour the composition uses goes through use(), so the sidecar is complete."""

    def __init__(self, brand: dict):
        cols = {k: _color.norm_hex(str(v)) for k, v in (brand.get("colors") or {}).items()}
        cols = {k: v for k, v in cols.items() if v}
        pal = {k: _color.norm_hex(str(v)) for k, v in (brand.get("palette") or {}).items()}
        self.all = sorted(set(cols.values()) | {v for v in pal.values() if v})
        if not self.all:
            sys.exit("error: the profile has no brand colours (brand.colors); run setup first")
        by_l = sorted(self.all, key=_color.luminance)
        self.light = next((cols[k] for k in ("background", "secondary", "text") if k in cols
                           and _color.luminance(cols[k]) > 0.6), by_l[-1])
        self.dark = next((cols[k] for k in ("primary", "text", "background") if k in cols
                          and _color.luminance(cols[k]) < 0.2), by_l[0])
        self.soft = next((cols[k] for k in ("secondary",) if k in cols and cols[k] != self.light
                          and _color.luminance(cols[k]) > 0.45), self.light)
        self.accent = cols.get("accent") or max(self.all, key=_color.chroma)
        self.uses: dict[str, list[str]] = {}

    def use(self, hx: str, where: str) -> str:
        self.uses.setdefault(hx, []).append(where)
        return hx

    def on(self, bg: str) -> str:
        """Text colour for a background: the brand light or dark with the better contrast."""
        return max((self.light, self.dark), key=lambda c: _color.contrast(c, bg))

    def emphasis_on(self, bg: str) -> str:
        """The accent if it reads on bg (3:1), else the most vivid brand colour that does, else on(bg)."""
        if _color.contrast(self.accent, bg) >= 3.0:
            return self.accent
        ok = [c for c in self.all if _color.contrast(c, bg) >= 3.0 and _color.chroma(c) > 0.2]
        return max(ok, key=_color.chroma) if ok else self.on(bg)


# ---------------------------------------------------------------- fonts
class Fonts:
    """Resolve each role to a font file in the project dir and remember where it came from."""

    def __init__(self, fonts_cfg: dict, home: Path | None, proj: Path):
        self.cfg, self.home, self.proj = fonts_cfg, home, proj
        self.faces = [f for f in (fonts_cfg.get("faces") or []) if isinstance(f, dict)]
        self.files = [f for f in (fonts_cfg.get("files") or []) if isinstance(f, str)]
        self.css: list[str] = []
        self.used: list[dict] = []
        self.google_cache: dict[str, list[dict] | None] = {}
        (proj / "fonts").mkdir(parents=True, exist_ok=True)

    def _abs(self, rel: str) -> Path | None:
        p = Path(rel).expanduser()
        if not p.is_absolute() and self.home:
            p = self.home / p
        return p if p.is_file() else None

    def _ship(self, src: Path, family: str, style: str, weight: int, declare_style: bool = True) -> str:
        import _fonts
        ext = _fonts.sniff(src.read_bytes()[:4]) or src.suffix
        name = f"{_fonts.file_name(family, style, weight, ext)}"
        shutil.copyfile(src, self.proj / "fonts" / name)
        fmt = {".ttf": "truetype", ".otf": "opentype", ".woff": "woff", ".woff2": "woff2"}.get(ext, "truetype")
        rule = (f'@font-face{{font-family:"{family}";src:url("fonts/{name}") format("{fmt}");'
                f'font-weight:{weight};' + (f"font-style:{style};" if declare_style else "") + "}")
        if rule not in self.css:
            self.css.append(rule)
        return name

    def _from_profile(self, family: str, role_names: tuple[str, ...], style: str, weight: int) -> Path | None:
        cands = [f for f in self.faces if f.get("family", "").lower() == family.lower() and f.get("style") == style]
        if cands:
            best = min(cands, key=lambda f: abs(int(f.get("weight") or 400) - weight))
            return self._abs(str(best.get("file") or ""))
        # owner's own files without a faces list: files[0] is the heading face, files[1] (if any) the body
        if not self.faces and self.cfg.get("source") == "files" and self.files and style == "normal":
            if any(r.startswith("display") for r in role_names):
                return self._abs(self.files[0])
            if any(r.startswith("body") for r in role_names):
                return self._abs(self.files[min(1, len(self.files) - 1)])
        return None

    def _from_google(self, family: str, style: str, weight: int) -> Path | None:
        import _fonts
        if family not in self.google_cache:
            try:
                self.google_cache[family] = _fonts.faces(family, want_italic=True)
            except (LookupError, OSError, ValueError):
                self.google_cache[family] = None
        got = [f for f in (self.google_cache[family] or []) if f["style"] == style]
        if not got:
            return None
        best = min(got, key=lambda f: abs(f["weight"] - weight))
        try:
            path, _ = _fonts.download(best, self.proj / "google-cache")
            return path
        except (OSError, ValueError):
            return None

    def get(self, role: str, family: str | None, style: str, weight: int, fallback: str = "Inter") -> str:
        """CSS font-family for one role (registers the @font-face) and record its source."""
        roles = (role,)
        if family:
            src = self._from_profile(family, roles, style, weight)
            source = "profile-file"
            if not src:
                src, source = self._from_google(family, style, weight), "google"
            if src:
                self._ship(src, family, style, weight)
                self.used.append({"role": role, "family": family, "style": style, "weight": weight,
                                  "source": source, "file": str(src)})
                return f"'{family}'"
        fb = fallback if fallback in BUNDLED else "Inter"
        fw = min(BUNDLED[fb], key=lambda x: abs(x - weight))
        f = ASSETS / "fonts" / BUNDLED[fb][fw]
        css_family = f"RR {fb}"
        if f.exists():
            self._ship(f, css_family, "normal", fw, declare_style=False)
        self.used.append({"role": role, "family": fb, "style": style, "weight": fw,
                          "source": "bundled-fallback" if f.exists() else "system-fallback",
                          "file": str(f) if f.exists() else None, "wanted": family})
        return f"'{css_family}'"


# ---------------------------------------------------------------- spec
def load_spec(path: str, dur: float) -> list[dict]:
    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.exit(f"error: cannot read spec {path} ({exc.__class__.__name__})")
    items = spec.get("items") if isinstance(spec, dict) else None
    if not items:
        sys.exit("error: spec has no items")
    out = []
    for n, it in enumerate(items, 1):
        kind = it.get("kind")
        if kind not in KINDS:
            sys.exit(f"error: item {n}: kind must be one of {', '.join(KINDS)}")
        s = float(it.get("start", 0))
        e = it.get("end")
        e = dur if e is None else float(e)
        s, e = (dur + s if s < 0 else s), (dur + e if e < 0 else e)
        s, e = max(0.0, s), min(dur, e)
        if e - s < 0.8:
            sys.exit(f"error: item {n} ({kind}) is {e - s:.2f}s long; give it at least 0.8 s")
        for (k, field), limit in LIMITS.items():
            v = it.get(field)
            if k == kind and isinstance(v, str) and len(v) > limit:
                sys.exit(f"error: item {n} ({kind}) {field} is {len(v)} characters (max {limit} for one line): "
                         f"shorten it in the plan; the engine never rewrites text")
        out.append({**it, "start": round(s, 3), "end": round(e, 3)})
    out.sort(key=lambda x: x["start"])
    for a, b in zip(out, out[1:]):
        if b["start"] < a["end"] - 1e-6:
            sys.exit(f"error: {a['kind']} ({a['start']}-{a['end']}) overlaps {b['kind']} ({b['start']}-{b['end']}): "
                     f"one idea at a time")
    for it in out:
        if it["kind"] == "hook" and not it.get("title"):
            sys.exit("error: hook needs a title")
        if it["kind"] == "lower_third" and not it.get("name"):
            sys.exit("error: lower_third needs a name")
    return out


def rot_box(x: float, y: float, w: float, h: float, deg: float) -> list[float]:
    """Axis-aligned bounds of a w x h box at (x, y) rotated about its centre."""
    r = math.radians(abs(deg))
    bw, bh = w * math.cos(r) + h * math.sin(r), w * math.sin(r) + h * math.cos(r)
    cx, cy = x + w / 2, y + h / 2
    return [round(cx - bw / 2, 1), round(cy - bh / 2, 1), round(bw, 1), round(bh, 1)]


# ---------------------------------------------------------------- composition
def build(items: list[dict], prof: dict, pal: Palette, fonts: Fonts, home: Path | None, proj: Path,
          w: int, h: int, dur: float, has_logo: Path | None) -> tuple[str, list[dict]]:
    brand = prof.get("brand") or {}
    fcfg = brand.get("fonts") or {}
    head, body, hand = fcfg.get("heading"), fcfg.get("body"), fcfg.get("hand")
    kinds = {it["kind"] for it in items}
    f_disp = fonts.get("display", head, "normal", 700)
    f_ital = fonts.get("display_italic", head, "italic", 400) if (kinds & {"hook"} or not hand) else None
    f_body = fonts.get("body", body, "normal", 400) if kinds & {"lower_third", "end_card"} else None
    f_bodyb = fonts.get("body_bold", body, "normal", 700) if "end_card" in kinds else None
    f_hand = None
    if "polaroid" in kinds:
        f_hand = fonts.get("hand", hand, "normal", 400, fallback="Caveat") if hand else f_ital
    s = w / 1080.0
    px = lambda v: f"{v * s:.1f}px"   # noqa: E731
    shadow = "0 18px 44px rgba(0,0,0,.28), 0 2px 6px rgba(0,0,0,.18)"
    layers, tweens, recs = [], [], []

    def fit(cls: str, text: str, mx: int, mn: int, avail: float, extra: str = "") -> str:
        """One line of exact text; shrinks from mx to mn px (never below) until it fits `avail` px."""
        return (f'<div class="fit {cls}" data-max="{mx * s:.1f}" data-min="{mn * s:.1f}" data-avail="{avail * s:.1f}" '
                f'style="font-size:{mx * s:.1f}px;{extra}">{html.escape(text)}</div>')

    for n, it in enumerate(items):
        k, st, en = it["kind"], it["start"], it["end"]
        i = f"ov{n}"
        out_at = max(st + 0.5, en - 0.35)
        if k == "hook":
            on_card = it.get("on", "card") != "light"
            bg = pal.use(pal.dark if on_card else pal.light, "hook.card")
            fg = pal.use(pal.on(bg), "hook.title")
            em = pal.use(pal.emphasis_on(bg), "hook.italic")
            rule = pal.use(pal.emphasis_on(bg), "hook.rule")
            border = "" if on_card else f"box-shadow:{shadow};"
            x, y, cw = 72, 260, 936          # cw = max width; the card shrinks to its text
            ch = 104 + 4 + 22 + 121 + (131 if it.get("italic") else 0)
            body_html = (f'<div class="rule" id="{i}r" style="background:{rule}"></div>'
                         + fit("disp", it["title"], 112, 72, cw - 128, f"color:{fg};font-family:{f_disp},serif;"
                               f"font-weight:700;line-height:1.08;letter-spacing:-0.02em;")
                         + (fit("ital", it["italic"], 112, 72, cw - 128, f"color:{em};font-family:{f_ital},serif;"
                                f"font-style:italic;font-weight:400;line-height:1.12;letter-spacing:-0.01em;")
                            if it.get("italic") else ""))
            layers.append(f'<div class="ov card" id="{i}" style="left:{px(x)};top:{px(y)};max-width:{px(cw)};'
                          f'padding:{px(52)} {px(64)};background:{bg};border-radius:{px(30)};{border}">{body_html}</div>')
            tweens += [f'tl.fromTo("#{i}",{{opacity:0,y:{40 * s:.0f}}},{{opacity:1,y:0,duration:0.55,ease:"power3.out"}},{st:.3f});',
                       f'tl.fromTo("#{i}r",{{scaleX:0}},{{scaleX:1,duration:0.5,ease:"power3.out"}},{st + 0.1:.3f});',
                       f'tl.fromTo("#{i} .disp",{{opacity:0,y:{26 * s:.0f}}},{{opacity:1,y:0,duration:0.5,ease:"power3.out"}},{st + 0.12:.3f});',
                       f'tl.fromTo("#{i} .ital",{{opacity:0,x:{-28 * s:.0f}}},{{opacity:1,x:0,duration:0.55,ease:"power3.out"}},{st + 0.3:.3f});',
                       f'tl.to("#{i}",{{opacity:0,y:{-24 * s:.0f},duration:0.35,ease:"power2.in"}},{out_at:.3f});']
            box = [x, y, cw, ch]
            text = {"title": it["title"], "italic": it.get("italic")}
        elif k == "lower_third":
            paper = pal.use(pal.light, "lower_third.paper")
            ink = pal.use(pal.on(paper), "lower_third.text")
            rule = pal.use(pal.emphasis_on(paper), "lower_third.rule")
            tape = pal.use(pal.soft if pal.soft != pal.light else pal.accent, "lower_third.tape")
            x, y, cw, deg = 72, 850, 800, -2.0      # cw = max width; the note shrinks to its text (min 560)
            ch = 36 + 84 + 30 + (77 if it.get("detail") else 0) + 30
            inner = (f'<div class="tape" style="background:{tape}"></div>'
                     + fit("disp", it["name"], 76, 64, cw - 84, f"color:{ink};font-family:{f_disp},serif;font-weight:700;"
                           "line-height:1.1;letter-spacing:-0.015em;")
                     + f'<div class="hair" id="{i}h" style="background:{rule}"></div>'
                     + (fit("body", it["detail"], 64, 64, cw - 84, f"color:{ink};opacity:.82;font-family:{f_body},"
                            "sans-serif;font-weight:400;line-height:1.2;letter-spacing:0;") if it.get("detail") else ""))
            layers.append(f'<div class="ov note" id="{i}" style="left:{px(x)};top:{px(y)};min-width:{px(560)};'
                          f'max-width:{px(cw)};padding:{px(36)} {px(42)} {px(30)};background:{paper};'
                          f'box-shadow:{shadow};">{inner}</div>')
            tweens += [f'tl.fromTo("#{i}",{{opacity:0,x:{-60 * s:.0f},rotation:-6}},{{opacity:1,x:0,rotation:{deg},duration:0.6,ease:"power3.out"}},{st:.3f});',
                       f'tl.fromTo("#{i}h",{{scaleX:0}},{{scaleX:1,duration:0.45,ease:"power3.out"}},{st + 0.25:.3f});',
                       f'tl.fromTo("#{i} .body",{{opacity:0}},{{opacity:0.82,duration:0.4,ease:"sine.out"}},{st + 0.35:.3f});',
                       f'tl.to("#{i}",{{opacity:0,x:{-40 * s:.0f},duration:0.3,ease:"power2.in"}},{out_at:.3f});']
            box = rot_box(x, y, cw, ch, deg)
            text = {"name": it["name"], "detail": it.get("detail")}
        elif k == "polaroid":
            frame = pal.use(pal.light, "polaroid.frame")
            ink = pal.use(pal.on(frame), "polaroid.caption")
            wash = pal.use(pal.light, "polaroid.wash")
            src_name, src_start = "base.mp4", float(it.get("src_start", st))
            if it.get("src"):
                sp = Path(it["src"]).expanduser()
                if not sp.is_absolute() and home:
                    sp = home / sp
                if not sp.is_file():
                    sys.exit(f"error: polaroid src not found: {it['src']}")
                src_name = f"broll{n}{sp.suffix.lower()}"
                shutil.copyfile(sp, proj / src_name)
                src_start = float(it.get("src_start", 0))
            d = en - st
            if it.get("bg", "blur") == "blur":
                # its own copy of the source: two nodes with one src/start/duration may be discovered twice
                bg_name = f"blur{n}{Path(src_name).suffix}"
                shutil.copyfile(proj / src_name, proj / bg_name)
                bgv = (f'<video id="{i}bv" class="clip bgv" src="{bg_name}" muted playsinline data-start="{st:.3f}" '
                       f'data-duration="{d:.3f}" data-media-start="{src_start:.3f}" data-track-index="2"></video>')
                wash_op = 0.55
            else:
                bgv, wash_op = "", 1.0
            soft = pal.use(pal.soft, "polaroid.bg")
            layers.append(f'<div class="ov full" id="{i}b">{bgv}<div class="wash" style="background:radial-gradient('
                          f'120% 80% at 50% 40%,{wash},{soft});opacity:{wash_op}"></div></div>')
            pw, ph, pad, cap_h, deg = 640, 660, 26, 130, 3.0 if n % 2 == 0 else -3.0
            cw, ch = pw + 2 * pad, pad + ph + cap_h
            x, y = (1080 - cw) / 2, 270
            cap = (fit("hand", it["caption"], 72, 64, pw, f"color:{ink};font-family:{f_hand},cursive;"
                       f"font-weight:400;{'font-style:italic;' if f_hand == f_ital else ''}line-height:1.2;"
                       "text-align:center;") if it.get("caption") else "")
            layers.append(f'<div class="ov pol" id="{i}" style="left:{px(x)};top:{px(y)};width:{px(cw)};height:{px(ch)};'
                          f'padding:{px(pad)} {px(pad)} 0;background:{frame};box-shadow:0 30px 60px rgba(0,0,0,.32),'
                          f'0 3px 8px rgba(0,0,0,.2);">'
                          f'<div class="photo" style="width:{px(pw)};height:{px(ph)}"><video id="{i}v" class="clip" src="{src_name}" muted '
                          f'playsinline data-start="{st:.3f}" data-duration="{d:.3f}" data-media-start="{src_start:.3f}" '
                          f'data-track-index="3"></video></div><div class="capline" style="height:{px(cap_h)}">{cap}</div></div>')
            tweens += [f'tl.fromTo("#{i}b",{{opacity:0}},{{opacity:1,duration:0.35,ease:"sine.out"}},{st:.3f});',
                       f'tl.fromTo("#{i}",{{opacity:0,y:{70 * s:.0f},rotation:{-deg * 2:.1f},scale:0.94}},'
                       f'{{opacity:1,y:0,rotation:{deg},scale:1,duration:0.65,ease:"power3.out"}},{st + 0.05:.3f});',
                       f'tl.to("#{i}",{{y:{-10 * s:.0f},duration:{max(0.2, d - 1.0):.3f},ease:"sine.inOut"}},{st + 0.7:.3f});',
                       f'tl.to("#{i}, #{i}b",{{opacity:0,duration:0.3,ease:"power2.in"}},{out_at:.3f});']
            box = rot_box(x, y, cw, ch, deg)
            text = {"caption": it.get("caption")}
        else:  # end_card
            dark_bg = it.get("on", "light") == "dark"
            bg = pal.use(pal.dark if dark_bg else pal.light, "end_card.bg")
            bg2 = pal.use(pal.soft if not dark_bg else pal.dark, "end_card.bg")
            ink = pal.use(pal.on(bg), "end_card.text")
            rule = pal.use(pal.emphasis_on(bg), "end_card.rule")
            pill = pal.use(pal.accent, "end_card.cta")
            pill_ink = pal.use(pal.on(pill), "end_card.cta_text")
            name = it.get("name") or (prof.get("business") or {}).get("name") or ""
            if has_logo:
                mark = f'<img class="logo" id="{i}m" src="{has_logo.name}" alt="" style="height:{px(300)}">'
                mark_h = 300
            else:
                if not name:
                    sys.exit("error: end_card needs a name (no logo and no business.name)")
                mark = fit("disp name", name, 120, 72, 760, f"color:{ink};font-family:{f_disp},serif;font-weight:700;"
                           "line-height:1.1;letter-spacing:-0.02em;text-align:center;")
                mark_h = 132
            parts = [f'<div class="mk" id="{i}m0">{mark}</div>', f'<div class="hair c" id="{i}h" style="background:{rule}"></div>']
            if it.get("address"):
                parts.append(fit("body st", it["address"], 64, 64, 760, f"color:{ink};font-family:{f_body},sans-serif;"
                                 "font-weight:400;line-height:1.3;text-align:center;"))
            if it.get("website"):
                parts.append(fit("body st", it["website"], 64, 64, 760, f"color:{ink};opacity:.78;font-family:{f_body},"
                                 "sans-serif;font-weight:400;line-height:1.3;text-align:center;"))
            if it.get("cta"):
                parts.append(f'<div class="pillwrap st"><div class="pill" id="{i}p" style="background:{pill};color:{pill_ink};'
                             f'font-family:{f_bodyb},sans-serif;padding:{px(26)} {px(60)};font-size:{px(64)};">'
                             f'{html.escape(it["cta"])}</div></div>')
            x, y, cw = 160, 340, 760
            ch = mark_h + 36 + 3 + 36 + (87 if it.get("address") else 0) + (87 if it.get("website") else 0) \
                + (163 if it.get("cta") else 0)
            layers.append(f'<div class="ov full" id="{i}" style="background:radial-gradient(130% 90% at 50% 30%,{bg},{bg2})">'
                          f'<div class="stack" style="left:{px(x)};top:{px(y)};width:{px(cw)}">{"".join(parts)}</div></div>')
            # everything is in and still within ~0.75 s, so even a short end card reads in full
            tweens += [f'tl.fromTo("#{i}",{{opacity:0}},{{opacity:1,duration:0.3,ease:"sine.out"}},{st:.3f});',
                       f'tl.fromTo("#{i}m0",{{opacity:0,scale:0.9,rotation:-8}},{{opacity:1,scale:1,rotation:0,duration:0.7,ease:"power3.out"}},{st + 0.05:.3f});',
                       f'tl.fromTo("#{i}h",{{scaleX:0}},{{scaleX:1,duration:0.4,ease:"power3.out"}},{st + 0.15:.3f});',
                       f'tl.fromTo("#{i} .st",{{opacity:0,y:{24 * s:.0f}}},{{opacity:1,y:0,duration:0.35,ease:"power3.out",stagger:0.08}},{st + 0.2:.3f});']
            if it.get("cta"):
                reps = max(0, int((en - st - 1.0) / 1.5) * 2 - 1)
                if reps > 0:
                    tweens.append(f'tl.to("#{i}p",{{scale:1.03,duration:0.75,ease:"sine.inOut",yoyo:true,repeat:{reps}}},{st + 0.9:.3f});')
            box = [x, y, cw, ch]
            text = {"name": None if has_logo else name, "address": it.get("address"), "website": it.get("website"),
                    "cta": it.get("cta"), "logo": has_logo.name if has_logo else None}
        recs.append({"kind": k, "start": st, "end": en, "box": [round(v * s, 1) for v in box], "text": text})

    font_css = "\n".join(fonts.css)
    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={w}, height={h}" />
<title>ReelReady overlays</title>
<script src="{'gsap.min.js' if (proj / 'gsap.min.js').exists() else 'https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js'}"></script>
<style>
{font_css}
body {{ margin:0; background:#000; }}
#root {{ position:relative; width:100%; height:100%; overflow:hidden; }}
#a-roll {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }}
.ov {{ position:absolute; box-sizing:border-box; }}
.full {{ inset:0; }}
.full .bgv {{ position:absolute; inset:-6%; width:112%; height:112%; object-fit:cover; filter:blur({28 * s:.0f}px) saturate(.9); }}
.wash {{ position:absolute; inset:0; }}
.fit {{ display:block; white-space:nowrap; width:max-content; }}
.card .rule {{ width:{px(84)}; height:{px(4)}; border-radius:{px(2)}; margin-bottom:{px(22)}; transform-origin:0 50%; }}
.note .tape {{ position:absolute; left:50%; top:{px(-18)}; width:{px(170)}; height:{px(40)}; margin-left:{px(-85)};
  opacity:.85; border-radius:{px(3)}; }}
.note .hair {{ width:100%; height:{px(2)}; margin:{px(14)} 0 {px(14)}; transform-origin:0 50%; }}
.pol .photo {{ position:relative; overflow:hidden; }}
.pol .photo video {{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }}
.pol .capline {{ display:flex; align-items:center; justify-content:center; }}
.stack {{ position:absolute; display:flex; flex-direction:column; align-items:center; }}
.stack .mk {{ display:flex; justify-content:center; width:100%; }}
.stack .logo {{ display:block; width:auto; max-width:100%; object-fit:contain; }}
.stack .hair.c {{ width:{px(120)}; height:{px(3)}; margin:{px(36)} 0; transform-origin:50% 50%; }}
.stack .body {{ margin-bottom:{px(10)}; }}
.pillwrap {{ margin-top:{px(34)}; }}
.pill {{ border-radius:999px; font-weight:700; line-height:1.2; letter-spacing:0.005em; white-space:nowrap; }}
</style>
</head>
<body>
<div id="root" data-composition-id="main" data-start="0" data-width="{w}" data-height="{h}" data-duration="{dur:.3f}">
  <video id="a-roll" class="clip" src="base.mp4" muted playsinline data-start="0" data-duration="{dur:.3f}" data-track-index="0"></video>
{chr(10).join("  " + x for x in layers)}
</div>
<script>
function fitAll() {{
  document.querySelectorAll(".fit").forEach(function (el) {{
    var s = parseFloat(el.dataset.max), mn = parseFloat(el.dataset.min), av = parseFloat(el.dataset.avail);
    el.style.fontSize = s + "px";
    while (el.offsetWidth > av && s > mn) {{ s -= 1; el.style.fontSize = s + "px"; }}
  }});
}}
function build() {{
  fitAll();
  const tl = gsap.timeline({{ paused: true }});
{chr(10).join("  " + t for t in tweens)}
  tl.set({{}}, {{}}, {dur:.3f});
  window.__timelines["main"] = tl;
}}
Promise.all(Array.from(document.fonts).map(function (f) {{ return f.load().catch(function () {{ return null; }}); }}))
  .then(function () {{ return document.fonts.ready; }}).then(build);
</script>
</body>
</html>
"""
    return doc, recs


def check_layout(recs: list[dict], w: int, h: int, band: tuple[float, float]) -> dict:
    s = w / 1080.0
    top, bottom, rail_x = SAFE_TOP * s, h - SAFE_BOTTOM * s, w - RAIL * s
    problems = []
    for r in recs:
        x, y, bw, bh = r["box"]
        if y < top - 0.5 or y + bh > bottom + 0.5:
            problems.append(f"{r['kind']} leaves the safe zone vertically ({y:.0f}..{y + bh:.0f})")
        if y + bh > h / 2 and x + bw > rail_x + 0.5:
            problems.append(f"{r['kind']} reaches the right button rail (right edge {x + bw:.0f} > {rail_x:.0f})")
        if x < 0 or x + bw > w:
            problems.append(f"{r['kind']} runs off the frame")
        if y < band[1] and y + bh > band[0]:
            problems.append(f"{r['kind']} overlaps the caption band ({band[0]:.0f}..{band[1]:.0f})")
    return {"inside_safe_zone": not any("safe zone" in p or "rail" in p or "off the frame" in p for p in problems),
            "clear_of_captions": not any("caption band" in p for p in problems), "problems": problems}


def main() -> None:
    ap = argparse.ArgumentParser(description="Branded overlay layer (hook, lower third, polaroid, end card).")
    ap.add_argument("video")
    ap.add_argument("--spec", required=True, help="overlays spec JSON (items with times and exact text)")
    ap.add_argument("--profile", required=True, help="<main>/.reelready/style-profile.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--home", default=None, help="main folder (profile paths are relative to it)")
    ap.add_argument("--caption-band", default=None, help="y0:y1 px kept free for captions (default 59-73%% of h)")
    ap.add_argument("--keep-project", default=None, help="keep the HyperFrames project in this dir")
    ap.add_argument("--no-render", action="store_true", help="build the project and the sidecar only")
    a = ap.parse_args()
    need("ffmpeg")
    if not a.no_render:
        need("npx")
    t0 = time.time()
    prof_path = Path(a.profile)
    try:
        prof = json.loads(prof_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.exit(f"error: cannot read profile {a.profile} ({exc.__class__.__name__})")
    info = video_info(a.video)
    dur, w, h = info["duration"], info["width"], info["height"]
    if not w or abs(w / h - 9 / 16) > 0.02:
        sys.exit(f"error: overlays.py draws 9:16 only ({w}x{h}); use the motion-graphics skill for other sizes")
    items = load_spec(a.spec, dur)
    if a.caption_band:
        y0, _, y1 = a.caption_band.partition(":")
        band = (float(y0), float(y1))
    else:
        band = (round(h * 0.59, 1), round(h * 0.73, 1))
    home = main_folder(a.home, prof_path)

    proj = Path(a.keep_project) if a.keep_project else Path(tempfile.mkdtemp(prefix="rr-overlays-"))
    proj.mkdir(parents=True, exist_ok=True)
    if not a.keep_project:
        atexit.register(shutil.rmtree, proj, True)
    shutil.copyfile(a.video, proj / "base.mp4")
    if (ASSETS / "vendor/gsap.min.js").exists():
        shutil.copyfile(ASSETS / "vendor/gsap.min.js", proj / "gsap.min.js")
    brand = prof.get("brand") or {}
    logo = None
    if brand.get("logo") and any(it["kind"] == "end_card" for it in items):
        lp = Path(str(brand["logo"])).expanduser()
        if not lp.is_absolute() and home:
            lp = home / lp
        if lp.is_file() and lp.suffix.lower() in (".png", ".jpg", ".jpeg", ".svg", ".webp"):
            logo = proj / f"logo{lp.suffix.lower()}"
            shutil.copyfile(lp, logo)
        else:
            print(f"warning: logo not found or not an image: {brand['logo']}; end card uses the business name",
                  file=sys.stderr)
    pal = Palette(brand)
    fonts = Fonts(brand.get("fonts") or {}, home, proj)
    doc, recs = build(items, prof, pal, fonts, home, proj, w, h, dur, logo)
    checks = check_layout(recs, w, h, band)
    if checks["problems"]:
        sys.exit("error: layout check failed: " + "; ".join(checks["problems"]))
    (proj / "index.html").write_text(doc, encoding="utf-8")
    shutil.rmtree(proj / "google-cache", ignore_errors=True)

    out = Path(a.out)
    side = {"video": str(Path(a.video).resolve()), "out": str(out.resolve()), "size": [w, h], "duration": dur,
            "fonts": fonts.used, "colors": {k: sorted(set(v)) for k, v in sorted(pal.uses.items())},
            "palette": pal.all, "items": recs, "caption_band": list(band),
            "safe_zone": {"top": SAFE_TOP * w / 1080, "bottom": SAFE_BOTTOM * w / 1080, "right_rail": RAIL * w / 1080},
            "checks": {k: v for k, v in checks.items() if k != "problems"},
            "hyperframes": HF_VERSION, "project": str(proj) if a.keep_project else None}
    out.parent.mkdir(parents=True, exist_ok=True)
    side_path = out.with_suffix(".overlays.json")
    if a.no_render:
        side_path.write_text(json.dumps(side, indent=2) + "\n", encoding="utf-8")
        print(f"built {proj / 'index.html'} ({len(items)} items); sidecar {side_path}")
        return

    env = {**os.environ, "HYPERFRAMES_SKIP_SKILLS": "1", "HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
    silent = proj / "overlays_silent.mp4"
    fps = str(int(round(info["fps"] or 30)))
    p = subprocess.run(["npx", "--yes", f"hyperframes@{HF_VERSION}", "render", str(proj), "-o", str(silent),
                        "--fps", fps, "--quality", "delivery", "--quiet"], env=env, capture_output=True, text=True)
    if p.returncode != 0 or not silent.exists():
        msg = (p.stderr or "") + (p.stdout or "")
        if "Low disk space" in msg:
            sys.exit("error: HyperFrames refused to render: the disk is almost full (it needs at least 1 GB free "
                     "for temp frames). Free some space and run this again.")
        sys.exit(f"error: hyperframes render failed:\n{msg[-1500:]}")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(silent), "-i", a.video, "-map", "0:v:0"]
    if info["has_audio"]:
        cmd += ["-map", "1:a:0", "-c:a", "copy"]
    run(cmd + ["-c:v", "libx264", "-profile:v", "high", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
               "-t", f"{dur:.3f}", "-movflags", "+faststart", str(out)])
    side_path.write_text(json.dumps(side, indent=2) + "\n", encoding="utf-8")
    srcs = sorted({f"{f['family']} ({f['source']})" for f in fonts.used})
    print(f"overlays {out}: {', '.join(it['kind'] for it in items)}; fonts {', '.join(srcs)}; "
          f"{len(pal.uses)} brand colours; via hyperframes@{HF_VERSION} in {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
