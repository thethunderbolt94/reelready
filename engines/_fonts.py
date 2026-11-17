"""Google Fonts (OFL) helpers shared by scripts/rr.py fonts and engines/overlays.py. Standard library only.

The css2 API answers a plain (non-browser) User-Agent with TrueType URLs, one per style/weight, which both
captions.py and HyperFrames accept. Files are sniffed by their magic bytes before they are trusted.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CSS2 = "https://fonts.googleapis.com/css2"
UA = "Mozilla/5.0 (compatible; ReelReady font fetch)"
MAX_FONT_BYTES = 8 * 1024 * 1024
FONT_MAGIC = {b"\x00\x01\x00\x00": ".ttf", b"true": ".ttf", b"OTTO": ".otf", b"wOFF": ".woff", b"wOF2": ".woff2"}
FACE = re.compile(r"@font-face\s*\{([^}]*)\}", re.S)


def _get(url: str, timeout: float = 20.0, limit: int = MAX_FONT_BYTES) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https hosts only)
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"too large: {url}")
    return data


def css2_url(family: str, axes: str | None) -> str:
    fam = family.strip()
    q = urllib.parse.quote(fam).replace("%20", "+") + (f":{axes}" if axes else "")
    return f"{CSS2}?family={q}&display=swap"


def faces(family: str, want_italic: bool = True) -> list[dict]:
    """[{family, style, weight, url}] for a Google family: regular 400 + 700 (+ italic 400 when asked).
    Tries the richest axis set first and falls back, because not every family has italics or a 700.
    Raises LookupError when Google Fonts does not know the family."""
    tries = (["ital,wght@0,400;0,700;1,400"] if want_italic else []) + ["wght@400;700", "wght@400", None]
    last = None
    for axes in tries:
        try:
            css = _get(css2_url(family, axes), limit=512 * 1024).decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:   # 400 = bad axes for this family (or unknown family)
            last = exc
            continue
        out, seen = [], set()
        for block in FACE.findall(css):
            style = re.search(r"font-style:\s*(\w+)", block)
            weight = re.search(r"font-weight:\s*(\d+)", block)
            url = re.search(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", block)
            if not url:
                continue
            key = ((style.group(1) if style else "normal"), int(weight.group(1)) if weight else 400)
            if key in seen:
                continue
            seen.add(key)
            out.append({"family": family, "style": key[0], "weight": key[1], "url": url.group(1)})
        if out:
            return out
    raise LookupError(f"'{family}' is not on Google Fonts ({last})")


def sniff(data: bytes) -> str | None:
    return FONT_MAGIC.get(data[:4])


def file_name(family: str, style: str, weight: int, ext: str = ".ttf") -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "", family) or "Font"
    return f"{base}-{weight}{'-italic' if style == 'italic' else ''}{ext}"


def download(face: dict, folder: Path, overwrite: bool = False) -> tuple[Path, bool]:
    """Save one face into folder. Returns (path, downloaded). Never overwrites unless asked."""
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / file_name(face["family"], face["style"], face["weight"])
    if dest.exists() and not overwrite:
        return dest, False
    data = _get(face["url"])
    ext = sniff(data)
    if not ext:
        raise ValueError(f"not a font file: {face['url']}")
    dest = dest.with_suffix(ext)
    if dest.exists() and not overwrite:
        return dest, False
    dest.write_bytes(data)
    return dest, True
