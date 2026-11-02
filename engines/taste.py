#!/usr/bin/env python3
"""ReelReady taste gate — fail an edit that ignored the owner's brand. Stdlib only.

    python3 engines/taste.py --profile style-profile.json [--plan plan.md] \
        [--captions captioned.captions.json] [--sound sound.sound.json] [--mix H1,C1,L2,O1,S2] [--strict]
        [--no-signature "<why no signature card fits>"]

qa.py proves the pixels and loudness are sound; this proves the render used THIS brand, not the kit
defaults. It reads the profile, the plan.md the user approved, and the sidecars the engines write
(captions.py -> <stem>.captions.json, sound.py -> <stem>.sound.json). No --mix -> profile.default_mix.

Rules (each prints one line, "TASTE ok|FAIL|note <rule>: <reason>"):
  brand-choices    plan.md has "## Brand choices" with >= 3 bullets, and every bullet names a brand
                   color hex, a brand font, "logo" (if brand.logo is set) or a 3-word phrase from
                   reference_style (pacing / caption_style / hook_patterns / music_use)
  accent-color     captions accent_color == brand.colors.accent (never the engine default #FFD60A)
  brand-font       brand.fonts.files non-empty -> captions font_source must be "brand"
  signature        exactly one signature move in the mix (hard rule 3): a card from
                   profile.house_style.signature or a signature-category card (X1-X6). None is a FAIL
                   unless --no-signature gives the reason (e.g. no card's needs could be met): then a note
  sound-preset     sound.json preset matches the mix's S card (S1 clean, S2 punchy, S3 cinematic,
                   S4 calm, S5 clean + music)
  palette-in-plan  the Brand choices section names >= 2 distinct brand colors (hex or role word)

"note" means the rule could not be checked (optional file absent, or the profile/mix gives nothing
to check against); notes never fail unless --strict. Never crashes on a missing optional file.
Last line is exactly one of:
  TASTE PASS (<n> rules)
  TASTE FAIL: generic edit, <k> rule(s): <rule>, <rule>
Exit 0 on pass, 1 on fail (or an unreadable profile).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # keep engines/ free of __pycache__
CARDS = Path(__file__).resolve().parent.parent / "styles" / "cards"

ENGINE_DEFAULT_ACCENT = "#FFD60A"
SOUND_PRESETS = {"S1": "clean", "S2": "punchy", "S3": "cinematic", "S4": "calm", "S5": "clean"}
RULES = ("brand-choices", "accent-color", "brand-font", "signature", "sound-preset", "palette-in-plan")
REF_KEYS = ("pacing", "caption_style", "hook_patterns", "music_use")
LOOSE_ROLES = ("text", "background")  # only count as a color role when written "<role> color"
WORD = re.compile(r"[a-z0-9]+(?:[.'-][a-z0-9]+)*")
HEX = re.compile(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b")


def norm_hex(h: str) -> str:
    h = h.strip().upper()
    if re.fullmatch(r"#[0-9A-F]{3}", h):
        h = "#" + "".join(c * 2 for c in h[1:])
    return h


def words(s: str) -> list[str]:
    return WORD.findall(s.lower())


def has_phrase(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase.lower())}(?![a-z0-9])", text.lower()) is not None


def load_json(path: str | None, label: str, notes: list[str]):
    """Parsed JSON, or None with a note when the optional file is absent/unreadable."""
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        notes.append(f"{label} not found: {path}")
        return None
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError) as exc:
        notes.append(f"{label} unreadable ({exc.__class__.__name__}): {path}")
        return None


def brand_section(plan: str) -> list[str] | None:
    """Bullet texts under '## Brand choices' (None if the heading is missing)."""
    lines = plan.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^\s*##\s+brand choices\s*:?\s*$", line, re.I):
            out = []
            for nxt in lines[i + 1:]:
                if re.match(r"^\s*#{1,2}\s", nxt):
                    break
                m = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)?\s*$", nxt)
                if m:
                    out.append((m.group(1) or "").strip())
            return out
    return None


def signature_cards() -> set[str]:
    """IDs of signature-category cards (X1-X6) from styles/cards; empty if the folder is missing."""
    out = set()
    for f in CARDS.glob("*.json"):
        try:
            c = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if c.get("category") == "signature" and c.get("id"):
            out.add(str(c["id"]).upper())
    return out


def parse_mix(s: str) -> list[str]:
    return [t.upper() for t in re.split(r"[\s,+]+|\band\b", s, flags=re.I) if t.strip()]


class Gate:
    def __init__(self, strict: bool):
        self.strict = strict
        self.results: list[tuple[str, str, str]] = []

    def ok(self, rule: str, why: str):
        self.results.append(("ok", rule, why))

    def fail(self, rule: str, why: str):
        self.results.append(("FAIL", rule, why))

    def note(self, rule: str, why: str):
        self.results.append(("FAIL" if self.strict else "note", rule, why + (" (--strict)" if self.strict else "")))


def main() -> None:
    ap = argparse.ArgumentParser(description="Taste gate: fail a render that ignored the brand.")
    ap.add_argument("--profile", required=True, help="<main>/.reelready/style-profile.json")
    ap.add_argument("--plan", default=None, help="<export_dir>/plan.md (approved version)")
    ap.add_argument("--captions", default=None, help="<stem>.captions.json written by captions.py")
    ap.add_argument("--sound", default=None, help="<stem>.sound.json written by sound.py")
    ap.add_argument("--mix", default=None, help="card IDs used, e.g. H1,C1,L2,O1,S2 (default: profile.default_mix)")
    ap.add_argument("--strict", action="store_true", help="notes (unchecked rules) count as FAILs")
    ap.add_argument("--no-signature", default=None, metavar="REASON",
                    help="no signature card fits this reel (say why); turns a missing signature into a note")
    a = ap.parse_args()

    try:
        prof = json.loads(Path(a.profile).read_text())
    except (OSError, ValueError) as exc:
        print(f"TASTE FAIL: cannot read profile {a.profile} ({exc.__class__.__name__})")
        sys.exit(1)

    brand = prof.get("brand") or {}
    colors = {k: norm_hex(v) for k, v in (brand.get("colors") or {}).items()
              if isinstance(v, str) and HEX.fullmatch(v.strip())}
    fonts = brand.get("fonts") or {}
    font_files = [f for f in (fonts.get("files") or []) if f]
    font_names = {v.strip() for k, v in fonts.items() if k not in ("source", "files") and isinstance(v, str) and v.strip()}
    font_names |= {Path(f).stem for f in font_files}
    logo = bool(brand.get("logo"))
    ref = prof.get("reference_style") or {}
    ref_phrases: set[str] = set()
    for k in REF_KEYS:
        vals = ref.get(k)
        for v in (vals if isinstance(vals, list) else [vals]):
            if isinstance(v, str):
                w = words(v)
                ref_phrases |= {" ".join(w[i:i + 3]) for i in range(len(w) - 2)}

    g = Gate(a.strict)
    io_notes: list[str] = []
    caps = load_json(a.captions, "captions.json", io_notes)
    snd = load_json(a.sound, "sound.json", io_notes)
    for n in io_notes:
        print(f"TASTE note input: {n}")

    if a.mix:
        mix, mix_src = parse_mix(a.mix), "--mix"
    else:
        mix, mix_src = [str(x).upper() for x in (prof.get("default_mix") or [])], "profile default_mix"

    # 1. brand-choices + 6. palette-in-plan
    if not a.plan or not Path(a.plan).exists():
        why = "no --plan given" if not a.plan else f"plan not found: {a.plan}"
        g.note("brand-choices", why)
        g.note("palette-in-plan", why)
    else:
        bullets = brand_section(Path(a.plan).read_text(errors="replace"))
        vocab = bool(colors or font_names or logo or ref_phrases)
        filled = [b for b in (bullets or []) if b]
        if bullets is None:
            g.fail("brand-choices", "plan.md has no '## Brand choices' section")
        elif not vocab:
            g.note("brand-choices", "profile has no brand colors, fonts, logo or reference style to name")
        elif len(filled) < 3:
            g.fail("brand-choices", f"{len(filled)} bullet(s) under '## Brand choices', need >= 3")
        else:
            def names_brand(b: str) -> bool:
                hexes = {norm_hex(h) for h in HEX.findall(b)}
                if hexes & set(colors.values()):
                    return True
                if any(has_phrase(b, f) for f in font_names):
                    return True
                if logo and has_phrase(b, "logo"):
                    return True
                bw = " " + " ".join(words(b)) + " "
                return any(f" {p} " in bw for p in ref_phrases)
            bad = [i + 1 for i, b in enumerate(filled) if not names_brand(b)]
            if bad:
                g.fail("brand-choices", f"bullet(s) {', '.join(map(str, bad))} of {len(filled)} name no brand "
                                        f"color, font, logo or reference phrase (generic)")
            else:
                g.ok("brand-choices", f"{len(filled)} bullets, each names a brand token")

        distinct = set(colors.values())
        need = min(2, len(distinct))
        if bullets is None:
            g.fail("palette-in-plan", "no '## Brand choices' section to name the palette")
        elif need == 0:
            g.note("palette-in-plan", "profile has no brand colors")
        else:
            text = "\n".join(bullets)
            seen = {norm_hex(h) for h in HEX.findall(text)} & distinct
            for role, hx in colors.items():
                pat = rf"\b{role}\s+colou?r\b" if role in LOOSE_ROLES else rf"\b{role}\b"
                if re.search(pat, text, re.I):
                    seen.add(hx)
            if len(seen) >= need:
                g.ok("palette-in-plan", f"{len(seen)} brand colors named: {', '.join(sorted(seen))}")
            else:
                g.fail("palette-in-plan", f"{len(seen)} brand color(s) named in Brand choices, need >= {need} "
                                          f"(hex or role: {', '.join(colors)})")

    # 2. accent-color
    accent = colors.get("accent")
    if caps is None:
        g.note("accent-color", "no captions.json (designed captions or none); check the frames by eye")
    else:
        got = norm_hex(str(caps.get("accent_color") or ""))
        if not accent:
            if got == ENGINE_DEFAULT_ACCENT:
                g.note("accent-color", f"profile has no accent color; captions used the engine default {got}")
            else:
                g.note("accent-color", f"profile has no accent color; captions used {got or 'none'}")
        elif got == accent:
            g.ok("accent-color", f"captions accent {got} = brand accent")
        elif got == ENGINE_DEFAULT_ACCENT:
            g.fail("accent-color", f"captions used the engine default {got}, brand accent is {accent}")
        else:
            g.fail("accent-color", f"captions accent {got or 'missing'} != brand accent {accent}")

    # 3. brand-font
    if not font_files:
        g.note("brand-font", "no brand font on file")
    elif caps is None:
        g.note("brand-font", f"brand font on file ({Path(font_files[0]).name}) but no captions.json to check")
    else:
        src = caps.get("font_source")
        if src == "brand":
            g.ok("brand-font", f"captions set in {caps.get('font_family') or 'the brand font'} (brand file)")
        else:
            g.fail("brand-font", f"brand font on file ({Path(font_files[0]).name}) but captions used "
                                 f"{caps.get('font_family') or '?'} ({src or 'unknown source'})")

    # 4. signature
    hs = prof.get("house_style") or {}
    sig = [str(x).upper() for x in (hs.get("signature") or [])]
    pool = sig + sorted(signature_cards() - set(sig))
    used = [c for c in mix if c in pool]
    if not mix:
        g.note("signature", "no --mix and no profile default_mix")
    elif len(used) > 1:
        g.fail("signature", f"stacked signature moves: {', '.join(used)} (hard rule 3: one per reel)")
    elif not used and a.no_signature:
        g.note("signature", f"no signature move: {a.no_signature}")
    elif not used and not sig:
        g.note("signature", "profile has no house_style.signature list and the mix has no X card")
    elif not used:
        g.fail("signature", f"no signature move: mix {'+'.join(mix)} ({mix_src}) has none of "
                            f"{', '.join(sig)} or an X card (or pass --no-signature \"<why>\")")
    elif hs.get("rotate") and len(sig) > 1 and str(hs.get("last_signature") or "").upper() == used[0]:
        g.note("signature", f"{used[0]} repeats last_signature while house_style.rotate is on")
    else:
        g.ok("signature", f"one signature move: {used[0]}")

    # 5. sound-preset
    s_cards = [c for c in mix if c in SOUND_PRESETS]
    if not s_cards:
        g.note("sound-preset", f"no S card in the mix ({mix_src}); sound.py default is S1 clean")
    elif len(s_cards) > 1:
        g.fail("sound-preset", f"two sound cards in the mix: {', '.join(s_cards)}; pick one")
    elif snd is None:
        g.note("sound-preset", f"mix has {s_cards[0]} but no sound.json to check")
    else:
        want, got = SOUND_PRESETS[s_cards[0]], str(snd.get("preset") or "")
        music_ok = s_cards[0] != "S5" or bool(snd.get("music"))
        if got == want and music_ok:
            g.ok("sound-preset", f"{s_cards[0]} -> preset {got}" + (" + music" if s_cards[0] == "S5" else ""))
        elif got != want:
            g.fail("sound-preset", f"mix has {s_cards[0]} ({want}) but sound ran preset {got or 'unknown'}")
        else:
            g.fail("sound-preset", "mix has S5 (music under) but sound ran without --music")

    g.results.sort(key=lambda r: RULES.index(r[1]))
    for status, rule, why in g.results:
        print(f"TASTE {status} {rule}: {why}")
    failed = [rule for status, rule, _ in g.results if status == "FAIL"]
    if failed:
        print(f"TASTE FAIL: generic edit, {len(failed)} rule(s): {', '.join(failed)}")
        sys.exit(1)
    print(f"TASTE PASS ({len(g.results)} rules)")


if __name__ == "__main__":
    main()
