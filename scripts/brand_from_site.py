#!/usr/bin/env python3
"""Read a business website's look (colours, fonts, logo) and propose brand settings. Standard library only.

    python3 scripts/brand_from_site.py <url | local index.html> [--out proposal.json]

Fetches the page and its same-origin stylesheets (never other hosts, never images), then reads:
  * CSS custom properties and every colour used (hex, rgb()), counted by how often rules use them
  * font-family stacks (which face the headings use, which the body uses, italic emphasis) and Google Fonts
    links (family names + axes)
  * logo candidates: <img>/<svg> whose src/alt/class/id says logo/mark/seal/brand, then apple-touch-icon,
    icon, og:image
and prints a plain-words proposal. --out writes the JSON (proposal.profile_merge is ready for
`rr.py profile-merge`, only after the owner confirms). Nothing is downloaded into the owner's folders: the
logo is only a list of URLs until the owner says yes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engines"))
import _color  # noqa: E402

UA = "Mozilla/5.0 (compatible; ReelReady brand reader)"
MAX_HTML, MAX_CSS, MAX_SHEETS = 3_000_000, 2_000_000, 12
GENERIC = {"serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui", "ui-sans-serif", "ui-serif",
           "ui-monospace", "-apple-system", "blinkmacsystemfont", "inherit", "initial", "unset", "emoji",
           "math", "fangsong", "segoe ui", "helvetica neue", "helvetica", "arial", "roboto", "times new roman",
           "georgia", "apple color emoji", "segoe ui emoji", "sans", "var"}
HEAD_SEL = re.compile(r"(^|[\s>+~,])(h1|h2|h3)\b|\.(display|title|heading|headline|hero)", re.I)
BODY_SEL = re.compile(r"^\s*(html|body|:root|p)\s*$", re.I)
CTA_SEL = re.compile(r"\.(cta|btn|button)|\bbutton\b", re.I)
LOGO_WORDS = re.compile(r"logo|seal|brandmark|wordmark|(^|[-_\s])mark([-_\s]|$)|brand", re.I)
COLOR_RE = re.compile(r"#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgba?\(\s*[\d.]+[\s,]+[\d.]+[\s,]+[\d.]+"
                      r"(?:\s*[,/]\s*[\d.%]+)?\s*\)")


def fetch(url: str, limit: int) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,text/css,*/*"})
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 (http/https/file only, checked by caller)
        data = r.read(limit + 1)
        final = r.geturl()
        charset = r.headers.get_content_charset() if hasattr(r, "headers") and r.headers else None
    if len(data) > limit:
        data = data[:limit]
    return data.decode(charset or "utf-8", "replace"), final


def origin(url: str) -> tuple[str, str]:
    u = urllib.parse.urlsplit(url)
    return u.scheme, u.netloc


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sheets, self.icons, self.og, self.imgs, self.svgs, self.styles, self.inline = [], [], [], [], [], [], []
        self._in_style = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        rel = a.get("rel", "").lower()
        if tag == "link" and "stylesheet" in rel and a.get("href"):
            self.sheets.append(a["href"])
        elif tag == "link" and ("icon" in rel) and a.get("href"):
            self.icons.append((rel, a["href"], a.get("sizes", "")))
        elif tag == "meta" and a.get("property", a.get("name", "")).lower() in ("og:image", "twitter:image"):
            if a.get("content"):
                self.og.append(a["content"])
        elif tag == "img" and (a.get("src") or a.get("data-src")):
            self.imgs.append(a)
        elif tag == "svg":
            self.svgs.append(a)
        elif tag == "style":
            self._in_style = True
        if a.get("style"):
            self.inline.append(a["style"])

    def handle_endtag(self, tag):
        if tag == "style":
            self._in_style = False

    def handle_data(self, data):
        if self._in_style:
            self.styles.append(data)


def to_hex(raw: str) -> str | None:
    raw = raw.strip()
    if raw.startswith("#"):
        if len(raw) == 9 and raw[7:].lower() == "00":
            return None   # fully transparent
        return _color.norm_hex(raw)
    nums = re.findall(r"[\d.]+%?", raw)
    if len(nums) < 3:
        return None
    if len(nums) >= 4:
        al = float(nums[3].rstrip("%")) / (100 if nums[3].endswith("%") else 1)
        if al < 0.5:
            return None   # a tint or shadow, not a brand colour
    vals = [float(n.rstrip("%")) * (2.55 if n.endswith("%") else 1) for n in nums[:3]]
    return _color.to_hex(*vals)


def google_families(href: str) -> list[dict]:
    u = urllib.parse.urlsplit(href)
    if "fonts.googleapis.com" not in u.netloc:
        return []
    out = []
    for fam in urllib.parse.parse_qs(u.query).get("family", []):
        for part in fam.split("|"):
            name, _, axes = part.partition(":")
            if name.strip():
                out.append({"family": name.replace("+", " ").strip(), "axes": axes or None,
                            "italic": "ital" in axes or "italic" in axes})
    return out


def first_family(stack: str) -> str | None:
    for f in stack.split(","):
        f = f.strip().strip("'\"").strip()
        if f and f.lower() not in GENERIC and not f.lower().startswith("var("):
            return f
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Propose brand colours, fonts and a logo from a website.")
    ap.add_argument("url", help="https://... or a local .html file")
    ap.add_argument("--out", default=None, help="write the full JSON here (else JSON goes to stdout)")
    a = ap.parse_args()

    target = a.url
    if Path(target).expanduser().is_file():
        target = Path(target).expanduser().resolve().as_uri()
    elif not re.match(r"https?://", target, re.I):
        target = "https://" + target
    if urllib.parse.urlsplit(target).scheme not in ("http", "https", "file"):
        sys.exit("error: give a web address (https://...) or a local .html file")
    try:
        page_html, final = fetch(target, MAX_HTML)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        sys.exit(f"error: could not open {a.url} ({exc.__class__.__name__}: {getattr(exc, 'reason', exc)}). "
                 f"Check the address, or skip this step and pick colours by hand.")
    page = Page()
    page.feed(page_html)
    home = origin(final)

    css_parts, fetched, skipped, gfonts = list(page.styles), [final], [], []
    queue = [urllib.parse.urljoin(final, h) for h in page.sheets]
    seen = set()
    while queue and len(fetched) <= MAX_SHEETS:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if "fonts.googleapis.com" in url:
            gfonts += google_families(url)
            continue
        if origin(url) != home:
            skipped.append({"url": url, "why": "other site (only this site's own stylesheets are read)"})
            continue
        try:
            css, _ = fetch(url, MAX_CSS)
        except (urllib.error.URLError, OSError, ValueError) as exc:
            skipped.append({"url": url, "why": f"could not fetch ({exc.__class__.__name__})"})
            continue
        fetched.append(url)
        css_parts.append(css)
        for imp in re.findall(r"@import\s+(?:url\()?['\"]?([^'\")\s;]+)", css):
            queue.append(urllib.parse.urljoin(url, imp))
    for s in page.styles:
        for imp in re.findall(r"@import\s+(?:url\()?['\"]?([^'\")\s;]+)", s):
            gfonts += google_families(urllib.parse.urljoin(final, imp))
    css = re.sub(r"/\*.*?\*/", "", "\n".join(css_parts), flags=re.S)
    css += "\n" + "\n".join(f"inline{{{s}}}" for s in page.inline)

    # custom properties, then var() resolution
    props: dict[str, str] = {}
    for name, val in re.findall(r"(--[\w-]+)\s*:\s*([^;{}]+)", css):
        props[name.strip()] = val.strip()

    def resolve(v: str, depth: int = 0) -> str:
        if depth > 6 or "var(" not in v:
            return v
        def rep(m):
            name, fb = m.group(1), (m.group(2) or "").strip()
            return props.get(name, fb)
        return resolve(re.sub(r"var\(\s*(--[\w-]+)\s*(?:,\s*([^()]*))?\)", rep, v), depth + 1)

    var_colors = {}
    for name, val in props.items():
        hx = None
        m = COLOR_RE.search(resolve(val))
        if m and m.group(0).strip() == resolve(val).strip():
            hx = to_hex(m.group(0))
        if hx:
            var_colors[name] = hx

    use, role_ev = Counter(), {"bg": [], "text": [], "cta": [], "em": []}
    fam_use, head_fams, body_fams, italic_head = Counter(), Counter(), Counter(), False
    for sel, decls in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        sel = sel.strip()
        if sel.startswith("@"):
            continue
        for prop, val in re.findall(r"([\w-]+)\s*:\s*([^;]+)", decls):
            prop, rv = prop.lower(), resolve(val)
            if prop.startswith("--"):
                continue
            cols = [h for h in (to_hex(c) for c in COLOR_RE.findall(rv)) if h]
            for hx in cols:
                use[hx] += 1
            sels = [x.strip() for x in sel.split(",")]
            if any(BODY_SEL.match(x) for x in sels) and cols:
                if prop in ("background", "background-color"):
                    role_ev["bg"].append((cols[0], f"{sel} {prop}"))
                elif prop == "color":
                    role_ev["text"].append((cols[0], f"{sel} color"))
            if CTA_SEL.search(sel) and prop in ("background", "background-color") and cols and ":hover" not in sel:
                role_ev["cta"].append((cols[0], f"{sel} background"))
            if re.search(r"\bem\b|italic", sel, re.I) and prop == "color" and cols:
                role_ev["em"].append((cols[0], f"{sel} color"))
            if prop in ("font-family", "font"):
                fam = first_family(rv if prop == "font-family" else rv.split(" ", 2)[-1])
                if fam:
                    fam_use[fam] += 1
                    if any(HEAD_SEL.search(x) for x in sels):
                        head_fams[fam] += 1
                    if any(BODY_SEL.match(x) for x in sels):
                        body_fams[fam] += 1
            if prop == "font-style" and "italic" in rv and any(HEAD_SEL.search(x) or " em" in x for x in sels):
                italic_head = True
    for hx in var_colors.values():
        use[hx] += 1

    colors, why = {}, {}
    ranked = [h for h, _ in use.most_common()]
    if role_ev["bg"]:
        colors["background"], why["background"] = role_ev["bg"][0][0], f"page background ({role_ev['bg'][0][1]})"
    elif ranked:
        colors["background"] = max(ranked[:8], key=_color.luminance)
        why["background"] = "lightest of the most-used colours"
    if role_ev["text"]:
        colors["text"], why["text"] = role_ev["text"][0][0], f"body text ({role_ev['text'][0][1]})"
    elif ranked:
        colors["text"] = min(ranked[:8], key=_color.luminance)
        why["text"] = "darkest of the most-used colours"
    named = {n: h for n, h in var_colors.items() if re.search(r"accent|brand|primary|cta|highlight", n, re.I)}
    acc_scores = Counter()
    for hx, ev in role_ev["cta"]:
        acc_scores[hx] += 3
    for hx, ev in role_ev["em"]:
        acc_scores[hx] += 2
    for n, hx in named.items():
        acc_scores[hx] += 2 if "accent" in n.lower() or "cta" in n.lower() else 1
    for hx in ranked:
        if _color.chroma(hx) > 0.25:
            acc_scores[hx] += min(use[hx], 6) * 0.5
    for hx in (colors.get("background"), colors.get("text")):
        acc_scores.pop(hx, None)
    if acc_scores:
        acc = acc_scores.most_common(1)[0][0]
        ev = [e for h, e in role_ev["cta"] + role_ev["em"] if h == acc]
        colors["accent"] = acc
        why["accent"] = f"used {use[acc]}x, " + ("; ".join(ev[:2]) if ev else "the most-used vivid colour")
    taken = {colors.get(k) for k in ("background", "text", "accent")}
    prim = next((h for n, h in var_colors.items() if re.search(r"primary|brand", n, re.I) and h not in taken), None)
    if prim:
        colors["primary"], why["primary"] = prim, "named primary/brand in the CSS"
    else:
        # the brand's dark may be the text colour too; never the accent or the background
        darks = [h for h in ranked if _color.luminance(h) < 0.2
                 and h not in (colors.get("accent"), colors.get("background"))]
        if darks:
            colors["primary"] = darks[0]
            why["primary"] = f"the most-used dark colour ({use[darks[0]]}x)"
    taken = {colors.get(k) for k in ("background", "text", "accent", "primary")}
    rest = [h for h in ranked if h not in taken and h in var_colors.values()] or [h for h in ranked if h not in taken]
    if rest:
        colors["secondary"] = rest[0]
        why["secondary"] = f"next most-used brand colour ({use[rest[0]]}x)"
    elif colors.get("background"):
        colors["secondary"], why["secondary"] = colors["background"], "same as the background (nothing else found)"

    palette = {}
    for n, hx in var_colors.items():
        clean = re.sub(r"^--|^(color|colour|clr|c)-", "", n.lstrip("-")).replace("-", " ").strip() or n
        if hx not in palette.values():
            palette[clean] = hx
    def near(a: str, b: str) -> bool:   # hover/active shades of a palette colour are not new colours
        return sum((x - y) ** 2 for x, y in zip(_color.rgb(a), _color.rgb(b))) < 45 ** 2

    for hx in ranked:
        if len(palette) >= 6:
            break
        if use[hx] >= 2 and not any(near(hx, p) for p in palette.values()):
            name, n = _color.plain_name(hx), 2
            while name in palette:
                name, n = f"{_color.plain_name(hx)} {n}", n + 1
            palette[name] = hx

    gnames = [g["family"] for g in gfonts]
    heading = (head_fams.most_common(1)[0][0] if head_fams else (gnames[0] if gnames else
               (fam_use.most_common(1)[0][0] if fam_use else None)))
    body = (body_fams.most_common(1)[0][0] if body_fams else next(
        (f for f, _ in fam_use.most_common() if f != heading), next((g for g in gnames if g != heading), None)))
    font_why = {"heading": "headings (h1-h3 / .display) use it" if head_fams else "first font the page loads",
                "body": "the page body uses it" if body_fams else "the other font the page uses"}
    gmap = {g["family"].lower(): g for g in gfonts}
    for role, fam in (("heading", heading), ("body", body)):
        if fam and fam.lower() in gmap:
            font_why[role] += "; on Google Fonts (free to download)"
    if italic_head:
        font_why["heading"] += "; the site sets an italic phrase in it"

    logos = []
    for img in page.imgs:
        blob = " ".join(img.get(k, "") for k in ("src", "data-src", "alt", "class", "id"))
        if LOGO_WORDS.search(blob):
            logos.append({"url": urllib.parse.urljoin(final, img.get("src") or img.get("data-src")),
                          "why": f"<img> whose name/alt/class says logo ({img.get('alt') or img.get('class') or ''})".strip()})
    for svg in page.svgs:
        blob = " ".join(svg.get(k, "") for k in ("class", "id", "aria-label"))
        if LOGO_WORDS.search(blob):
            logos.append({"url": None, "why": f"inline <svg> logo ({blob.strip()}); save it from the site by hand"})
    for rel, href, sizes in sorted(page.icons, key=lambda x: ("apple" not in x[0], -int((x[2] or "0x0").split("x")[0] or 0)
                                                              if (x[2] or "").split("x")[0].isdigit() else 0)):
        logos.append({"url": urllib.parse.urljoin(final, href), "why": f"<link rel={rel}> {sizes}".strip()})
    for og in page.og:
        logos.append({"url": urllib.parse.urljoin(final, og), "why": "og:image (often a photo, not the logo)"})

    fonts = {"heading": heading, "body": body, "source": "website"}
    brand = {"colors": colors, "palette": palette, "fonts": {k: v for k, v in fonts.items() if v},
             "colors_source": "website"}
    result = {
        "source": a.url, "fetched": fetched, "skipped": skipped,
        "proposal": {"brand": brand, "logo_candidates": logos[:6],
                     "profile_merge": {"brand": brand}},
        "evidence": {"colors": why, "fonts": font_why, "italic_emphasis": italic_head},
        "google_fonts": gfonts, "custom_properties": {k: v for k, v in props.items() if k in var_colors},
        "colors_by_use": [{"hex": h, "uses": n, "name": _color.plain_name(h)} for h, n in use.most_common(12)],
        "fonts_by_use": [{"family": f, "uses": n} for f, n in fam_use.most_common(6)],
    }
    lines = [f"From {a.url} ({len(fetched)} file(s) read):"]
    for role in ("primary", "secondary", "accent", "text", "background"):
        if role in colors:
            lines.append(f"  {role:10} {colors[role]}  {_color.plain_name(colors[role]):14} {why[role]}")
    if palette:
        lines.append("  palette    " + ", ".join(f"{n} {h}" for n, h in palette.items()))
    for role in ("heading", "body"):
        if fonts[role]:
            lines.append(f"  {role:10} {fonts[role]}: {font_why[role]}")
    if logos:
        lines.append(f"  logo       {logos[0]['url'] or '(inline svg)'}: {logos[0]['why']}")
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("\n".join(lines))
        print(f"Full proposal: {a.out}")
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
