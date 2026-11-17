"""Colour helpers (hex parsing, WCAG contrast, plain names, the caption accent pick). Standard library only."""
from __future__ import annotations

import colorsys
import re

HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
CAPTION_STROKE = "#121212"   # captions.py outline
CAPTION_TEXT = "#FFFFFF"     # captions.py word colour


def norm_hex(h: str) -> str | None:
    h = (h or "").strip()
    if not re.fullmatch(r"#?(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3}|[0-9a-fA-F]{8})", h):
        return None
    h = h.lstrip("#").upper()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h[:6]


def rgb(h: str) -> tuple[int, int, int]:
    h = norm_hex(h) or "#000000"
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def to_hex(r: float, g: float, b: float) -> str:
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(v))) for v in (r, g, b))


def luminance(h: str) -> float:
    def ch(v: int) -> float:
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def hls(h: str) -> tuple[float, float, float]:
    r, g, b = rgb(h)
    return colorsys.rgb_to_hls(r / 255, g / 255, b / 255)


def chroma(h: str) -> float:
    r, g, b = rgb(h)
    return (max(r, g, b) - min(r, g, b)) / 255


def mix(a: str, b: str, t: float) -> str:
    ra, rb = rgb(a), rgb(b)
    return to_hex(*(x + (y - x) * t for x, y in zip(ra, rb)))


def plain_name(h: str) -> str:
    """A rough everyday name ("warm brown", "cream") so an owner can confirm a swatch without hex codes."""
    hue, light, sat = hls(h)
    if light > 0.93:
        return "off-white" if chroma(h) < 0.08 else "very pale " + _hue(hue)
    if light < 0.12:
        return "near-black"
    if sat < 0.12 or chroma(h) < 0.08:
        return "grey" if 0.3 < light < 0.75 else ("light grey" if light >= 0.75 else "charcoal")
    base = _hue(hue)
    if light > 0.8:
        return "cream" if base in ("orange", "yellow") else "pale " + base
    if light < 0.3:
        return "deep " + ("brown" if base in ("orange", "red") and sat < 0.7 else base)
    if base == "orange" and light < 0.55:
        return "terracotta" if sat > 0.4 else "warm brown"
    return base


def _hue(hue: float) -> str:
    d = hue * 360
    for limit, name in ((15, "red"), (45, "orange"), (65, "yellow"), (160, "green"), (195, "teal"),
                        (255, "blue"), (290, "purple"), (335, "pink"), (361, "red")):
        if d < limit:
            return name
    return "red"


def accent_report(h: str) -> dict:
    """Why a colour does or does not work as the caption emphasis colour (white words, #121212 stroke)."""
    c_stroke = contrast(h, CAPTION_STROKE)
    c_text = contrast(h, CAPTION_TEXT)
    lum, chrom = luminance(h), chroma(h)
    problems = []
    if lum > 0.8:
        problems.append("too close to white")
    if lum < 0.03:
        problems.append("too close to black")
    if c_stroke < 3.0:
        problems.append(f"hard to read on the dark caption outline ({c_stroke:.1f}:1, need 3:1)")
    if c_text < 1.4:
        problems.append(f"looks like the white caption words ({c_text:.1f}:1)")
    if chrom < 0.2:
        problems.append("too grey to stand out as a highlight")
    return {"hex": norm_hex(h), "ok": not problems, "problems": problems,
            "contrast_on_outline": round(c_stroke, 2), "contrast_vs_white": round(c_text, 2),
            "score": round(chrom * min(c_stroke, 7.0) * (1.0 if not problems else 0.0), 3)}


def recommend_accent(colors: dict, palette: dict | None = None) -> dict:
    """Pick the caption emphasis colour from the brand. The brand accent wins when it works; else the most
    vivid readable brand colour; else a lighter tint of the brand accent (said plainly)."""
    cands: list[tuple[str, str]] = []
    for role in ("accent", "primary", "secondary"):
        if norm_hex(str(colors.get(role) or "")):
            cands.append((f"brand {role}", norm_hex(colors[role])))
    for name, v in (palette or {}).items():
        if norm_hex(str(v or "")):
            cands.append((f"palette '{name}'", norm_hex(v)))
    for role, v in colors.items():
        if role not in ("accent", "primary", "secondary") and norm_hex(str(v or "")):
            cands.append((f"brand {role}", norm_hex(v)))
    seen, reports = set(), []
    for label, hx in cands:
        if hx in seen:
            continue
        seen.add(hx)
        reports.append({"from": label, **accent_report(hx)})
    if not reports:
        return {"hex": None, "from": None, "reason": "the profile has no brand colours yet", "checked": []}
    first = reports[0]
    if first["from"] == "brand accent" and first["ok"]:
        pick, why = first, "your brand accent reads well over video with the caption outline"
    else:
        good = sorted((r for r in reports if r["ok"]), key=lambda r: -r["score"])
        if good:
            pick = good[0]
            why = (f"your brand accent is {', '.join(first['problems'])}; {pick['from']} is the most vivid brand "
                   f"colour that reads well" if first["from"] == "brand accent" else
                   f"{pick['from']} is the most vivid brand colour that reads well")
        else:
            base = first["hex"]
            tint = base
            for i in range(1, 11):
                tint = mix(base, "#FFFFFF", i * 0.08)
                if accent_report(tint)["ok"]:
                    break
            pick = {"from": f"lighter tint of {first['from']}", **accent_report(tint)}
            why = (f"none of your brand colours reads well over video ({first['from']}: "
                   f"{', '.join(first['problems'])}), so this is a lighter tint of it")
    return {"hex": pick["hex"], "from": pick["from"], "name": plain_name(pick["hex"]),
            "reason": why, "contrast_on_outline": pick["contrast_on_outline"], "checked": reports}
