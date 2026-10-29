#!/usr/bin/env python3
"""Build the ReelReady style guide page.

Reads styles/cards/*.json (+ the SVG sketches they point to), styles/mixes.json and
styles/presets.json (business-type house styles), validates them, and writes styleguide/index.html: one self-contained file with
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
    ("sound", "Sound", "How it sounds: voice polish, hits on the cuts, music under you. Pick one."),
]
CAT_KEYS = [c[0] for c in CATEGORIES]
ENGINES = {"captions", "overlay", "cut", "motion", "composite", "sound"}
NEEDS = {"matting", "transcript", "assets:logo", "assets:music", "broll"}
FIELDS = ["id", "category", "name", "oneliner", "description", "prompt", "engine",
          "needs", "pairs_with", "avoid_with", "sketch", "duration_hint"]

FALLBACK_CONFIG = {"brand": {"name": "ReelReady", "by": "Suhaas Builds", "url": ""},
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


PRESET_FIELDS = ["type", "match", "default_mix", "signature", "pacing", "sound", "notes"]
MIX_EXTRA_CATS = {"layout", "broll", "outro", "motion", "proof"}
SIG_CATS = {"signature", "motion", "proof", "broll"}


def load_presets(cards):
    """styles/presets.json: ids exist, mix shape, avoid_with respected, neighbours visibly different."""
    path = STYLES / "presets.json"
    if not path.exists():
        return [], []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [], [f"presets.json: invalid JSON ({exc})"]
    by_id = {c["id"]: c for c in cards}
    presets = doc.get("presets", [])
    errors, types = [], [p.get("type") for p in presets]

    def clash(ids):
        return sorted({f"{a}+{b}" for a in ids for b in ids
                       if a < b and (b in by_id[a]["avoid_with"] or a in by_id[b]["avoid_with"])})

    for p in presets:
        t = p.get("type", "?")
        missing = [k for k in PRESET_FIELDS if k not in p]
        if missing:
            errors.append(f"preset {t}: missing fields {missing}")
            continue
        mix, sig = p["default_mix"], p["signature"]
        unknown = [i for i in mix + sig if i not in by_id]
        if unknown:
            errors.append(f"preset {t}: unknown ids {unknown}")
            continue
        cats = [by_id[i]["category"] for i in mix]
        if not 5 <= len(mix) <= 6:
            errors.append(f"preset {t}: default_mix needs 5-6 cards, has {len(mix)}")
        for one in ("hook", "captions", "sound"):
            if cats.count(one) != 1:
                errors.append(f"preset {t}: default_mix needs exactly one {one} card")
        extra = [i for i, c in zip(mix, cats) if c not in MIX_EXTRA_CATS | {"hook", "captions", "sound"}]
        if extra:
            errors.append(f"preset {t}: default_mix may not hold {extra} (signature cards go in signature)")
        if len(sig) != 3 or len(set(sig)) != 3:
            errors.append(f"preset {t}: signature needs 3 different cards")
        bad = [i for i in sig if by_id[i]["category"] not in SIG_CATS]
        if bad:
            errors.append(f"preset {t}: signature cards must be X/M/P/B, not {bad}")
        if set(mix) & set(sig):
            errors.append(f"preset {t}: {sorted(set(mix) & set(sig))} in both default_mix and signature")
        if p["sound"] not in mix or by_id[p["sound"]]["category"] != "sound":
            errors.append(f"preset {t}: sound {p['sound']} must be the S card in default_mix")
        if p["pacing"] not in ("fast", "medium", "calm"):
            errors.append(f"preset {t}: pacing must be fast|medium|calm")
        if not p["match"]:
            errors.append(f"preset {t}: match keywords empty")
        for s in [None] + sig:
            bad = clash(mix + ([s] if s else []))
            if bad:
                errors.append(f"preset {t}: avoid_with clash {bad}" + (f" with signature {s}" if s else ""))
    if len(set(types)) != len(types):
        errors.append("presets.json: duplicate types")
    for p in presets:
        bad = [n for n in p.get("near", []) if n not in types or n == p.get("type")]
        if bad or len(p.get("near", [])) != 2:
            errors.append(f"preset {p.get('type')}: near needs 2 other preset types, bad {bad}")
    if doc.get("fallback") not in types:
        errors.append(f"presets.json: fallback {doc.get('fallback')!r} is not a preset type")
    for key, cat in (("sound_scale", "sound"), ("hook_scale", "hook")):
        bad = [i for i in doc.get(key, []) if i not in by_id or by_id[i]["category"] != cat]
        if bad:
            errors.append(f"presets.json: {key} has non-{cat} ids {bad}")
    if errors:
        return presets, errors
    for a, b in zip(presets, presets[1:]):
        first = lambda p, cat: next(i for i in p["default_mix"] if by_id[i]["category"] == cat)
        same = [cat for cat in ("hook", "captions", "sound") if first(a, cat) == first(b, cat)]
        if set(a["signature"]) == set(b["signature"]) or a["signature"][0] == b["signature"][0]:
            same.append("signature")
        if same:
            errors.append(f"presets {a['type']} / {b['type']} are neighbours but share {same}")
    return presets, errors


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def build(check_only=False, quiet=False):
    cfg = load_config()
    cards, errors = load_cards()
    mixes, mix_errors = load_mixes({c["id"] for c in cards})
    errors += mix_errors
    presets, preset_errors = load_presets(cards) if not errors else ([], [])
    errors += preset_errors
    if errors:
        for e in errors:
            print("error:", e)
        return False
    if check_only:
        if not quiet:
            print(f"ok: {len(cards)} cards, {len(mixes)} mixes, {len(presets)} presets valid")
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
                .replace("__CATS__", str(len(CATEGORIES)))
                .replace("__HERO_FAN__", hero)
                .replace("__DATA__", blob))
    OUT.write_text(html, encoding="utf-8")
    if not quiet:
        print(f"wrote {OUT.relative_to(ROOT)} ({len(cards)} cards, {len(html.encode()) // 1024} KB)")
    return True


if __name__ == "__main__":
    ok = build(check_only="--check" in sys.argv)
    sys.exit(0 if ok else 1)
