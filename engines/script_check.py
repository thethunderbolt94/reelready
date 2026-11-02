#!/usr/bin/env python3
"""ReelReady script check: fail a script that invents facts or reads like an ad. Stdlib only.

    python3 engines/script_check.py --script script.md --profile style-profile.json \
        [--work-dir "<main folder>/.reelready/work"] [--chat owner.txt] [--seconds 30]

The reelready-script skill writes script.md in a fixed shape (see
.claude/skills/reelready-script/references/formats.md). This parses that shape and checks it
against the REAL inputs: profile fields and past-reel transcripts, not just the script's own table.

Rules (each prints one line, "SCRIPT ok|FAIL <rule>: <reason>"):
  draft-banner     first non-blank line starts "DRAFT - written by AI"
  flagged          "## Hook" and "## Beats" headings carry [GENERATED - approve?]
  structure        meta line names structure (hook, context, payoff | list | before, after |
                   question, answer) and format (talking-points | word-for-word)
  length           spoken words <= seconds x 2.5 words/s + 15 percent. talking-points: words in
                   double quotes in Hook and Beats, plus 8 per beat line with no quote (said in
                   the owner's own words). word-for-word: every Hook and Beats word.
  hook-length      hook under 8 spoken words
  banned           Hook and Beats contain nothing from engines/banned.txt
  facts-table      "## Facts used" has >= 1 row "- <fact> | <source>"
  numbers-sourced  every number in Hook and Beats (digits or number words) appears in a Facts row,
                   unless it sits inside [ASK: ...]. A price ($4, four dollars) must match a price
                   in the Facts: "3 days" does not source "a $3 fee"
  sources-real     every Facts source is one of:
                     profile <dotted.field>            field exists, non-empty, shares a word with the fact
                     your past reel <job>: "<quote>"   <work-dir>/<job>/transcript.json (or
                                                       draft.words.json) contains the quote
                     you told me today: "<what>"       with --chat: the quote must be in that file
                                                       (the owner's own messages, saved verbatim);
                                                       always listed in the output
Seconds: --seconds, else profile.script.seconds, else 30.
Last line is exactly one of:
  SCRIPT PASS (<n> rules)
  SCRIPT FAIL: <k> rule(s): <rule>, <rule>
Exit 0 on pass, 1 on fail or an unreadable script/profile.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

WORDS_PER_SEC = 2.5
SLACK = 1.15
UNQUOTED_BEAT_WORDS = 8
STRUCTURES = ("hook, context, payoff", "list", "before, after", "question, answer")
FORMATS = ("talking-points", "word-for-word")
FLAG = "[GENERATED - approve?]"
BANNED_FILE = Path(__file__).with_name("banned.txt")

NUM_WORDS = {
    "zero": 0, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
    "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100, "thousand": 1000, "million": 1_000_000, "dozen": 12, "half": 0.5,
    "twice": 2,
}
STOP = set("the a an and or of to in on at for with is are was we our you your it this that "
           "these those my me i be by from as".split())
QUOTE_RE = re.compile(r'["“]([^"”]+)["”]')
ASK_RE = re.compile(r"\[ASK:[^\]]*\]", re.I)


def norm_words(s: str) -> list[str]:
    s = s.lower().replace("’", "'")
    return re.findall(r"[a-z0-9$.']+", s)


def norm_text(s: str) -> str:
    return " ".join(w.strip(".'") for w in norm_words(s) if w.strip(".'"))


def numbers_in(s: str) -> set[float]:
    """Numeric values mentioned in s, from digits ($4.50, 7am, 4,700) or number words.
    "one", "once", "first", "second" are left out: too common in plain speech ("this one")."""
    vals: set[float] = set()
    s = ASK_RE.sub(" ", s)
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", s):
        try:
            vals.add(float(m.group().replace(",", "")))
        except ValueError:
            pass
    for w in re.findall(r"[a-z]+", s.lower()):
        if w in NUM_WORDS:
            vals.add(float(NUM_WORDS[w]))
    return vals


PRICE_RE = re.compile(
    r"[$\u00a3\u20ac]\s?(\d[\d,]*(?:\.\d+)?)"
    r"|(\d[\d,]*(?:\.\d+)?|[a-z]+)\s+(?:dollars?|bucks?|cents?|pounds?|euros?|rupees?)\b", re.I)


def prices_in(s: str) -> set[float]:
    """Values said as money ($4, 4 dollars, four bucks). A price must be sourced as a price:
    "3 days" in the Facts does not cover "a $3 fee"."""
    vals: set[float] = set()
    for m in PRICE_RE.finditer(ASK_RE.sub(" ", s)):
        tok = (m.group(1) or m.group(2) or "").replace(",", "").lower()
        try:
            vals.add(float(tok))
        except ValueError:
            if tok in NUM_WORDS:
                vals.add(float(NUM_WORDS[tok]))
    return vals


def parse(text: str) -> dict:
    lines = text.splitlines()
    out = {"banner": "", "meta": "", "sections": {}, "headings": {}}
    for ln in lines:
        if ln.strip():
            out["banner"] = ln.strip()
            break
    cur = None
    for i, ln in enumerate(lines):
        if ln.startswith("# Script:"):
            for nxt in lines[i + 1:]:
                if nxt.strip():
                    out["meta"] = nxt.strip()
                    break
        m = re.match(r"^##\s+(.+?)\s*$", ln)
        if m:
            head = m.group(1)
            name = re.sub(r"\[.*?\]", "", head).strip().lower()
            cur = name
            out["sections"][cur] = []
            out["headings"][cur] = head
            continue
        if cur is not None and ln.strip():
            out["sections"][cur].append(ln.strip())
    return out


def load_banned() -> list[tuple[str, re.Pattern]]:
    pats = []
    if not BANNED_FILE.exists():
        return pats
    for ln in BANNED_FILE.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        if ln.startswith("re:"):
            pats.append((ln[3:], re.compile(ln[3:], re.I | re.M)))
        else:
            pats.append((ln, re.compile(r"(?<![\w-])" + re.escape(ln) + r"(?![\w-])", re.I)))
    return pats


def dotted(profile: dict, path: str):
    cur = profile
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def transcript_text(work: Path | None, job: str) -> str | None:
    if work is None:
        return None
    for name in ("transcript.json", "draft.words.json"):
        p = work / job / name
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(d, dict) and d.get("words"):
                return " ".join(str(w.get("w", "")) for w in d["words"])
            if isinstance(d, dict) and d.get("segments"):
                return " ".join(str(s.get("text", "")) for s in d["segments"])
            if isinstance(d, list):
                return " ".join(str(w.get("w", "")) for w in d if isinstance(w, dict))
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Check a ReelReady script.md")
    ap.add_argument("--script", required=True)
    ap.add_argument("--profile", required=True)
    ap.add_argument("--work-dir")
    ap.add_argument("--chat", help="owner's messages from this chat, verbatim, one per line")
    ap.add_argument("--seconds", type=float)
    a = ap.parse_args()

    try:
        text = Path(a.script).read_text(encoding="utf-8")
        profile = json.loads(Path(a.profile).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"SCRIPT FAIL: cannot read input ({e})")
        return 1
    work = Path(a.work_dir) if a.work_dir else None
    chat = None
    if a.chat:
        try:
            chat = norm_text(Path(a.chat).read_text(encoding="utf-8"))
        except OSError:
            print(f"SCRIPT FAIL: cannot read --chat {a.chat}")
            return 1
    sc = parse(text)
    secs = a.seconds or (profile.get("script") or {}).get("seconds") or 30
    hook = sc["sections"].get("hook", [])
    beats = sc["sections"].get("beats", [])
    spoken_area = "\n".join(re.sub(r"^\d+[.)]\s*", "", ln) for ln in hook + beats)
    meta = sc["meta"].lower()
    fmt = next((f for f in FORMATS if f"format: {f}" in meta), None)

    results: list[tuple[str, bool, str]] = []

    def rule(name: str, ok: bool, why: str):
        results.append((name, ok, why))

    rule("draft-banner", sc["banner"].startswith("DRAFT - written by AI"),
         "banner present" if sc["banner"].startswith("DRAFT - written by AI")
         else "first line must start 'DRAFT - written by AI'")

    missing = [k for k in ("hook", "beats") if FLAG not in sc["headings"].get(k, "")]
    rule("flagged", not missing,
         "Hook and Beats flagged" if not missing else f"no {FLAG} on: {', '.join(missing) or '?'}")

    struct = next((s for s in STRUCTURES if f"structure: {s}" in meta), None)
    rule("structure", bool(struct and fmt),
         f"{struct} / {fmt}" if struct and fmt else
         "meta line needs 'structure: <hook, context, payoff|list|before, after|question, answer>' "
         "and 'format: <talking-points|word-for-word>'")

    def spoken(lines: list[str]) -> list[str]:
        words: list[str] = []
        for ln in lines:
            body = re.sub(r"^\d+[.)]\s*", "", ln)
            if fmt == "word-for-word":
                words += norm_words(ASK_RE.sub(" ", body))
                continue
            qs = QUOTE_RE.findall(body)
            if qs:
                for q in qs:
                    words += norm_words(q)
            elif lines is beats:
                words += ["_"] * UNQUOTED_BEAT_WORDS
        return words

    budget = int(secs * WORDS_PER_SEC * SLACK)
    n_spoken = len(spoken(hook)) + len(spoken(beats))
    rule("length", n_spoken <= budget,
         f"{n_spoken} spoken words, budget {budget} for {secs:g} s")

    hook_words = spoken(hook)
    if not hook_words and hook:
        hook_words = norm_words(hook[0])
    rule("hook-length", 0 < len(hook_words) < 8,
         f"hook {len(hook_words)} words" + ("" if 0 < len(hook_words) < 8 else ", must be 1-7"))

    hits = [label for label, pat in load_banned() if pat.search(spoken_area)]
    rule("banned", not hits, "clean" if not hits else "found: " + ", ".join(hits))

    rows = []
    for ln in sc["sections"].get("facts used", []):
        if ln.startswith("-") and "|" in ln:
            fact, src = ln[1:].split("|", 1)
            rows.append((fact.strip(), src.strip()))
    rule("facts-table", bool(rows) and all(f and s for f, s in rows),
         f"{len(rows)} fact rows" if rows else "no '## Facts used' rows like '- <fact> | <source>'")

    sourced: set[float] = set()
    for f, s in rows:
        sourced |= numbers_in(f) | numbers_in(s)
    src_prices: set[float] = set()
    for f, src in rows:
        src_prices |= prices_in(f) | prices_in(src)
    loose = sorted(numbers_in(spoken_area) - sourced)
    loose += [v for v in sorted(prices_in(spoken_area) - src_prices) if v not in loose]
    rule("numbers-sourced", not loose,
         "every number sourced" if not loose else
         "not in Facts (or mark [ASK: ...]): " + ", ".join(f"{v:g}" for v in loose))

    bad, today = [], []
    for fact, src in rows:
        low = src.lower()
        q = QUOTE_RE.search(src)
        if low.startswith("profile "):
            field = src.split(None, 1)[1].strip().split()[0]
            val = dotted(profile, field)
            sval = json.dumps(val) if not isinstance(val, str) else val
            fw = {w for w in norm_words(fact) if w not in STOP}
            if val in (None, "", [], {}):
                bad.append(f"'{fact}': profile field {field} missing or empty")
            elif fw and not (fw & set(norm_words(sval))):
                bad.append(f"'{fact}': not in profile {field}")
        elif low.startswith("your past reel"):
            m = re.match(r"your past reel\s+([^\s:]+)", src, re.I)
            job = m.group(1) if m else ""
            tx = transcript_text(work, job)
            if not q:
                bad.append(f"'{fact}': past reel source needs the quoted line")
            elif tx is None:
                bad.append(f"'{fact}': no transcript for reel {job or '?'}"
                           + ("" if work else " (pass --work-dir)"))
            elif norm_text(q.group(1)) not in norm_text(tx):
                bad.append(f"'{fact}': quote not found in reel {job}")
        elif low.startswith("you told me today"):
            today.append(fact)
            if chat is not None:
                if not q:
                    bad.append(f"'{fact}': today source needs the owner's quoted words")
                elif norm_text(q.group(1)) not in chat:
                    bad.append(f"'{fact}': quote not in what the owner said (--chat)")
        else:
            bad.append(f"'{fact}': unknown source form '{src[:40]}'")
    rule("sources-real", not bad,
         f"{len(rows) - len(today)} checked, {len(today)} from today's chat" if not bad
         else "; ".join(bad))

    for name, ok, why in results:
        print(f"SCRIPT {'ok' if ok else 'FAIL'} {name}: {why}")
    if today:
        print("SCRIPT note today-only facts (the owner should double-check): " + "; ".join(today))
    failed = [n for n, ok, _ in results if not ok]
    if failed:
        print(f"SCRIPT FAIL: {len(failed)} rule(s): {', '.join(failed)}")
        return 1
    print(f"SCRIPT PASS ({len(results)} rules)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
