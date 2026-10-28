#!/usr/bin/env python3
"""Build the ReelReady style guide page.

Reads styles/cards/*.json (+ the SVG sketches they point to) and styles/mixes.json,
validates them, and writes styleguide/index.html: one self-contained file with
inline CSS, JS and SVGs. Standard library only.

    python3 styleguide/build.py          # build
    python3 styleguide/build.py --check  # validate only, write nothing
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
STYLES = ROOT / "styles"
CARDS_DIR = STYLES / "cards"
OUT = HERE / "index.html"
TEMPLATE = HERE / "template.html"

CATEGORIES = [
    ("hook", "Hook", "The first three seconds. Pick one."),
    ("captions", "Captions", "Word for word, always. Pick one look."),
    ("layout", "Layout", "Where you sit on screen, and what sits with you."),
    ("proof", "Proof", "Real reviews, real prices, real address. Never invented."),
    ("broll", "B-roll", "Show what you're talking about."),
    ("signature", "Signature", "The “how did they edit that” moment. One per idea."),
    ("motion", "Motion + pace", "Energy between the words."),
    ("outro", "Outro", "How it ends, and what people do next."),
]
CAT_KEYS = [c[0] for c in CATEGORIES]
ENGINES = {"captions", "overlay", "cut", "motion", "composite"}
NEEDS = {"matting", "transcript", "assets:logo", "assets:music", "broll"}
FIELDS = ["id", "category", "name", "oneliner", "description", "prompt", "engine",
          "needs", "pairs_with", "avoid_with", "sketch", "duration_hint"]

FALLBACK_CONFIG = {"brand": {"name": "ReelReady", "by": "Thrive Labs", "url": ""},
                   "styleguide": {"port": 4810}}


def load_config():
    """Brand strings + port from reelready.config.json, with safe fallbacks."""
    cfg = json.loads(json.dumps(FALLBACK_CONFIG))
    path = ROOT / "reelready.config.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            brand = data.get("brand") or {}
            for k in ("name", "by", "url"):
                if isinstance(brand.get(k), str) and brand[k].strip():
                    cfg["brand"][k] = brand[k].strip()
            port = ((data.get("styleguide") or {}).get("port")
                    or (data.get("ports") or {}).get("styleguide")
                    or data.get("styleguide_port"))
            if isinstance(port, int) and 0 < port < 65536:
                cfg["styleguide"]["port"] = port
        except (OSError, ValueError) as exc:
            print(f"warning: could not read reelready.config.json ({exc}); using defaults")
    return cfg


def card_sort_key(card):
    num = re.sub(r"\D", "", card["id"]) or "0"
    return (CAT_KEYS.index(card["category"]), int(num), card["id"])


def load_cards():
    errors, cards = [], []
    files = sorted(CARDS_DIR.glob("*.json"))
    if not files:
        errors.append(f"no cards found in {CARDS_DIR}")
    for f in files:
        try:
            card = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as exc:
            errors.append(f"{f.name}: invalid JSON ({exc})")
            continue
        missing = [k for k in FIELDS if k not in card]
        if missing:
            errors.append(f"{f.name}: missing fields {missing}")
            continue
        if f.stem != card["id"]:
            errors.append(f"{f.name}: file name must match id {card['id']}")
        if card["category"] not in CAT_KEYS:
            errors.append(f"{card['id']}: unknown category {card['category']}")
            continue
        if card["engine"] not in ENGINES:
            errors.append(f"{card['id']}: unknown engine {card['engine']}")
        bad = [n for n in card["needs"] if n not in NEEDS]
        if bad:
            errors.append(f"{card['id']}: unknown needs {bad}")
        sk = STYLES / card["sketch"]
        if not sk.exists():
            errors.append(f"{card['id']}: sketch not found at styles/{card['sketch']}")
            card["_svg"] = ""
        else:
            raw = sk.read_text(encoding="utf-8")
            if len(raw.encode("utf-8")) > 2048:
                print(f"warning: {card['sketch']} is over 2 KB")
            card["_svg"] = inline_svg(raw)
        cards.append(card)

    ids = [c["id"] for c in cards]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        errors.append(f"duplicate ids: {sorted(dupes)}")
    known = set(ids)
    for c in cards:
        for key in ("pairs_with", "avoid_with"):
            unknown = [x for x in c[key] if x not in known]
            if unknown:
                errors.append(f"{c['id']}: {key} references unknown ids {unknown}")
    cards.sort(key=card_sort_key)
    return cards, errors


def inline_svg(raw):
    """Strip the XML prolog and the per-file <style> (the page styles sketches itself)."""
    raw = re.sub(r"<\?xml[^>]*\?>", "", raw)
    raw = re.sub(r"<style>.*?</style>", "", raw, flags=re.S)
    raw = raw.replace('width="90" height="160"', "")
    return raw.replace("<svg ", '<svg aria-hidden="true" focusable="false" ', 1).strip()


def load_mixes(known):
    path = STYLES / "mixes.json"
    if not path.exists():
        return [], []
    try:
        mixes = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [], [f"mixes.json: invalid JSON ({exc})"]
    errors = []
    for m in mixes:
        unknown = [i for i in m.get("ids", []) if i not in known]
        if unknown:
            errors.append(f"mix {m.get('name')}: unknown ids {unknown}")
    return mixes, errors


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def build(check_only=False, quiet=False):
    cfg = load_config()
    cards, errors = load_cards()
    mixes, mix_errors = load_mixes({c["id"] for c in cards})
    errors += mix_errors
    if errors:
        for e in errors:
            print("error:", e)
        return False
    if check_only:
        if not quiet:
            print(f"ok: {len(cards)} cards, {len(mixes)} mixes valid")
        return True

    data = {
        "brand": cfg["brand"],
        "categories": [{"key": k, "label": l, "blurb": b} for k, l, b in CATEGORIES],
        "cards": cards,
        "mixes": mixes,
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    by_id = {c["id"]: c["_svg"] for c in cards}
    hero = "".join(
        f'<div class="fan-item fan-{n}"><span class="fan-code">{cid}</span>{by_id.get(cid, "")}</div>'
        for n, cid in enumerate(["H1", "X1", "C1"]) if cid in by_id)

    html = TEMPLATE.read_text(encoding="utf-8")
    brand = cfg["brand"]
    html = (html.replace("__BRAND_NAME__", esc(brand["name"]))
                .replace("__BRAND_BY__", esc(brand["by"]))
                .replace("__BRAND_URL__", esc(brand["url"] or "#"))
                .replace("__COUNT__", str(len(cards)))
                .replace("__HERO_FAN__", hero)
                .replace("__DATA__", blob))
    OUT.write_text(html, encoding="utf-8")
    if not quiet:
        print(f"wrote {OUT.relative_to(ROOT)} ({len(cards)} cards, {len(html.encode()) // 1024} KB)")
    return True


if __name__ == "__main__":
    ok = build(check_only="--check" in sys.argv)
    sys.exit(0 if ok else 1)
