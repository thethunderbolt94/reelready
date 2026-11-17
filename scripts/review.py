#!/usr/bin/env python3
"""ReelReady review contract: <export>/review-request.json (written by the edit skill before render) and
<export>/review.json (written by the Studio's Review page). Standard library only.

Used by `rr.py review-request`, `rr.py wait-review` and studio/serve.py. The full contract, with an
example, is in engines/README.md ("Review contract").
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import tempfile
from pathlib import Path

REQUEST = "review-request.json"
REVIEW = "review.json"
KINDS = {"hook", "lower_third", "end_card", "cta", "post_caption", "other"}
ACTIONS = {"approve", "edit", "reject"}
CUT_KINDS = {"talking", "broll"}
XFADE = 0.08   # render_cut.py crossfade between kept ranges (seconds)


def write_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def request_hash(path: Path) -> str:
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:16]


# ---------------------------------------------------------------- building the request
def cuts_from_edl(edl: dict, label: str | None = None) -> list[dict]:
    """One cut per EDL keep[] range, in play order, with draft times and trim bounds.
    Bounds: a cut may grow into removed time but never into another kept range (or past the clip)."""
    keep = edl.get("keep") or []
    src = edl.get("source") or ""
    dur = float(edl.get("duration") or 0) or max((float(k["end"]) for k in keep), default=0.0)
    by_start = sorted(keep, key=lambda k: float(k["start"]))
    cuts, t = [], 0.0
    xf = min([XFADE] + [(float(k["end"]) - float(k["start"])) / 3 for k in keep])  # same as render_cut.py
    for i, k in enumerate(keep):
        s, e = float(k["start"]), float(k["end"])
        j = by_start.index(k)
        lo = float(by_start[j - 1]["end"]) if j > 0 else 0.0
        hi = float(by_start[j + 1]["start"]) if j + 1 < len(by_start) else dur
        length = e - s
        cuts.append({"index": i, "kind": "broll" if k.get("reason") == "broll" else "talking",
                     "label": label or Path(src).name, "source": src,
                     "start": round(s, 3), "end": round(e, 3),
                     "bounds": [round(min(lo, s), 3), round(max(hi, e), 3)],
                     "draft_start": round(t, 3), "draft_end": round(t + length, 3)})
        t += length - (xf if i + 1 < len(keep) else 0)
    return cuts


# ---------------------------------------------------------------- validation
def check_request(req: dict) -> list[str]:
    errs = []
    if not isinstance(req, dict):
        return ["review-request.json must be a JSON object"]
    for f in ("title", "draft"):
        if not isinstance(req.get(f), str) or not req.get(f):
            errs.append(f"'{f}' is missing")
    items = req.get("generated")
    if not isinstance(items, list):
        errs.append("'generated' must be a list (empty when Claude wrote nothing)")
        items = []
    ids = set()
    for n, it in enumerate(items):
        if not isinstance(it, dict) or not it.get("id") or not isinstance(it.get("text"), str):
            errs.append(f"generated[{n}] needs an id and text")
            continue
        if it["id"] in ids:
            errs.append(f"generated id '{it['id']}' is used twice")
        ids.add(it["id"])
        if it.get("kind") not in KINDS:
            errs.append(f"generated '{it['id']}' kind must be one of {sorted(KINDS)}")
    for n, c in enumerate(req.get("cuts") or []):
        try:
            lo, hi = float(c["bounds"][0]), float(c["bounds"][1])
            if not (lo <= float(c["start"]) < float(c["end"]) <= hi):
                errs.append(f"cuts[{n}] start/end must sit inside bounds")
        except (KeyError, TypeError, ValueError, IndexError):
            errs.append(f"cuts[{n}] needs start, end and bounds [min, max]")
        if c.get("kind", "talking") not in CUT_KINDS:
            errs.append(f"cuts[{n}] kind must be talking or broll")
    hook_ids = set()
    for n, h in enumerate(req.get("hook_options") or []):
        if not isinstance(h, dict) or not h.get("id") or not isinstance(h.get("text"), str):
            errs.append(f"hook_options[{n}] needs an id and text")
            continue
        hook_ids.add(h["id"])
        if h.get("source") not in ("owner", "generated"):
            errs.append(f"hook option {h['id']} source must be 'owner' or 'generated'")
        if h.get("source") == "generated" and h.get("item_id") not in ids:
            errs.append(f"hook option {h['id']} is generated, so its item_id must name a generated item")
    return errs


def check_review(review: dict, req: dict) -> list[str]:
    """Problems with a review against its request. Empty list = complete and in bounds."""
    errs = []
    if not isinstance(review, dict):
        return ["review must be a JSON object"]
    decisions = review.get("decisions")
    if not isinstance(decisions, dict):
        return ["'decisions' must be an object {item id: {action, text?}}"]
    items = {it["id"]: it for it in (req.get("generated") or []) if isinstance(it, dict) and it.get("id")}
    for iid in items:
        d = decisions.get(iid)
        if not isinstance(d, dict) or d.get("action") not in ACTIONS:
            errs.append(f"no decision for '{iid}' (approve, edit or reject)")
        elif d["action"] == "edit" and not (isinstance(d.get("text"), str) and d["text"].strip()):
            errs.append(f"'{iid}' is marked edit but has no new text")
    for iid in decisions:
        if iid not in items:
            errs.append(f"decision for unknown item '{iid}'")
    cuts = req.get("cuts") or []
    for t in review.get("trims") or []:
        try:
            c = cuts[int(t["cut"])]
            s, e = float(t["start"]), float(t["end"])
            lo, hi = float(c["bounds"][0]), float(c["bounds"][1])
            if not (lo - 1e-6 <= s < e <= hi + 1e-6):
                errs.append(f"trim for cut {t['cut']} is outside {lo}-{hi} s")
        except (KeyError, TypeError, ValueError, IndexError):
            errs.append(f"bad trim {t!r}")
    for s in review.get("swaps") or []:
        try:
            c = cuts[int(s["cut"])]
            if c.get("kind") != "broll":
                errs.append(f"cut {s['cut']} is not a b-roll shot, so it can't be swapped")
            if not (s.get("library_item") or {}).get("path"):
                errs.append(f"swap for cut {s['cut']} needs library_item.path")
        except (KeyError, TypeError, ValueError, IndexError):
            errs.append(f"bad swap {s!r}")
    hooks = {h["id"]: h for h in (req.get("hook_options") or []) if isinstance(h, dict) and h.get("id")}
    if hooks:
        hid = review.get("hook")
        if hid not in hooks:
            errs.append("pick a hook (A or B)")
        elif hooks[hid].get("source") == "generated":
            d = decisions.get(hooks[hid].get("item_id")) or {}
            if d.get("action") == "reject":
                errs.append(f"hook {hid} is a generated line you rejected; approve or edit it, or pick the other hook")
    return errs


# ---------------------------------------------------------------- freshness
def fresh_review(export_dir: Path) -> dict | None:
    """review.json if it exists and is newer than review-request.json (else None)."""
    req, rev = Path(export_dir) / REQUEST, Path(export_dir) / REVIEW
    if not req.exists() or not rev.exists():
        return None
    if rev.stat().st_mtime_ns <= req.stat().st_mtime_ns:
        return None
    try:
        return json.loads(rev.read_text(encoding="utf-8"))
    except ValueError:
        return None


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")
