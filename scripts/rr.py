#!/usr/bin/env python3
"""ReelReady helper: paths, newest clip, export folders, keys, profile, palette, music ducking.

Stdlib only. Run from anywhere:  python3 scripts/rr.py <command> [...]

  where [--json]                 main-folder paths (raw footage, exports, work, profile, env)
  newest [--n N]                 newest video file(s) in "raw footage"
  export-dir <slug>              create exports/<YYYY-MM-DD>-<slug>/ (+ matching work dir), print JSON
  run -- <cmd ...>               run <cmd> from the repo with .venv on PATH and .reelready/.env loaded
  set-key <assemblyai|elevenlabs>  read a key from stdin, save to <main>/.reelready/.env (never printed)
  profile-merge <file.json|->    deep-merge JSON into <main>/.reelready/style-profile.json
  house-style [--profile P] [--type T] [--apply] [--force]
                                 match the business to a styles/presets.json house style, print it as JSON;
                                 --apply merges default_mix + house_style into the profile
                                 (keeps a non-empty default_mix unless --force)
  next-signature [--profile P] [--commit]
                                 this reel's signature card (rotates house_style.signature after
                                 last_signature); --commit saves it as last_signature
  palette <image> [--n 5]        dominant brand colors of an image (logo) as hex
  duck-filter <transcript.json> [--duration S]  ffmpeg volume filter: music -18 dB under speech
  join-drafts <out.mp4> <draft_01.mp4> <draft_02.mp4> ...  multi-clip: concat render_cut drafts
                                 (stream copy) and merge their .words.json side files with time offsets
"""
import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
POINTER = REPO / ".reelready" / "home.json"
DEFAULT_HOME = Path.home() / "Desktop" / "AI Video Editor"
FOLDERS = ["raw footage", "references", "assets", "exports"]
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".3gp", ".hevc"}
KEY_NAMES = {"assemblyai": "ASSEMBLYAI_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}


def config():
    try:
        return json.loads((REPO / "reelready.config.json").read_text())
    except Exception:
        return {"brand": {"name": "ReelReady", "by": "Suhaas Builds"}}


def main_folder():
    env = os.environ.get("REELREADY_HOME")
    if env:
        return Path(env).expanduser()
    if POINTER.exists():
        try:
            return Path(json.loads(POINTER.read_text())["main_folder"]).expanduser()
        except Exception:
            pass
    if DEFAULT_HOME.exists():
        return DEFAULT_HOME
    return None


def paths():
    home = main_folder()
    if home is None:
        return {"configured": False, "repo": str(REPO), "main_folder": None}
    rr = home / ".reelready"
    return {
        "configured": home.exists(),
        "repo": str(REPO),
        "main_folder": str(home),
        "raw_footage": str(home / "raw footage"),
        "references": str(home / "references"),
        "assets": str(home / "assets"),
        "exports": str(home / "exports"),
        "work": str(rr / "work"),
        "profile": str(rr / "style-profile.json"),
        "profile_exists": (rr / "style-profile.json").exists(),
        "env_file": str(rr / ".env"),
        "venv_python": str(REPO / ".venv" / "bin" / "python"),
    }


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def need_home():
    p = paths()
    if not p.get("configured"):
        die("No main folder yet. Run setup (say: set up reelready) or scripts/init.py --path <folder>.", 2)
    return p


def slugify(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return (s[:40].rstrip("-")) or "reel"


def load_env_file(path):
    out = {}
    p = Path(path)
    if not p.exists():
        return out
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def deep_merge(base, extra):
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = v
    return base


# ---------------------------------------------------------------- commands
def cmd_where(args):
    p = paths()
    if "--json" in args:
        print(json.dumps(p, indent=2))
        return
    if not p.get("main_folder"):
        print("Main folder: not set up yet")
        return
    for k, v in p.items():
        print(f"{k:16} {v}")


def cmd_newest(args):
    p = need_home()
    n = int(args[args.index("--n") + 1]) if "--n" in args else 1
    raw = Path(p["raw_footage"])
    clips = [f for f in raw.rglob("*") if f.is_file() and f.suffix.lower() in VIDEO_EXT and not f.name.startswith(".")]
    if not clips:
        die('No video files in "raw footage" yet.', 3)
    clips.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    for f in clips[:n]:
        print(f)


def cmd_export_dir(args):
    p = need_home()
    if not args:
        die("usage: rr.py export-dir <slug>")
    base = f"{_dt.date.today().isoformat()}-{slugify(' '.join(args))}"
    name, i = base, 2
    while (Path(p["exports"]) / name).exists():
        name, i = f"{base}-{i}", i + 1
    exp = Path(p["exports"]) / name
    work = Path(p["work"]) / name
    exp.mkdir(parents=True)
    work.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"slug": name, "export_dir": str(exp), "work_dir": str(work)}, indent=2))


def cmd_run(args):
    if "--" in args:
        args = args[args.index("--") + 1:]
    if not args:
        die("usage: rr.py run -- <command ...>")
    env = dict(os.environ)
    p = paths()
    if p.get("env_file"):
        for k, v in load_env_file(p["env_file"]).items():
            env.setdefault(k, v)
    # Homebrew installs land outside a fresh shell's PATH on a new Mac; add them so ffmpeg is found.
    extra = [d for d in ("/opt/homebrew/bin", "/usr/local/bin")
             if Path(d).is_dir() and d not in env.get("PATH", "").split(os.pathsep)]
    if extra:
        env["PATH"] = os.pathsep.join([env.get("PATH", "")] + extra)
    venv_bin = REPO / ".venv" / "bin"
    if venv_bin.exists():
        env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
        env["VIRTUAL_ENV"] = str(REPO / ".venv")
    if p.get("main_folder"):
        env["REELREADY_HOME"] = p["main_folder"]
    sys.exit(subprocess.call(args, cwd=str(REPO), env=env))


def cmd_set_key(args):
    p = need_home()
    if not args or args[0] not in KEY_NAMES:
        die("usage: rr.py set-key <assemblyai|elevenlabs>  (key on stdin)")
    if sys.stdin.isatty():
        import getpass
        key = getpass.getpass("Paste your key and press Enter (it won't show): ").strip()
    else:
        key = sys.stdin.read().strip()
    if not key or any(c.isspace() for c in key):
        die("No key received (or it contained spaces). Nothing saved.")
    name = KEY_NAMES[args[0]]
    env_path = Path(p["env_file"])
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [l for l in (env_path.read_text().splitlines() if env_path.exists() else []) if not l.startswith(name + "=")]
    lines.append(f"{name}={key}")
    env_path.write_text("\n".join(lines) + "\n")
    os.chmod(env_path, 0o600)
    print(f"Saved {name} to {env_path} (not shown, file is private to you).")


def cmd_profile_merge(args):
    p = need_home()
    if not args:
        die("usage: rr.py profile-merge <file.json|->")
    extra = json.loads(sys.stdin.read() if args[0] == "-" else Path(args[0]).read_text())
    print(f"Profile updated: {merge_profile(p['profile'], extra)}")


def merge_profile(prof_path, extra):
    """Deep-merge `extra` into the profile at prof_path (created if missing), stamp updated."""
    prof_path = Path(prof_path)
    prof = json.loads(prof_path.read_text()) if prof_path.exists() else {"schema_version": 1}
    now = _dt.datetime.now().isoformat(timespec="seconds")
    prof.setdefault("created", now)
    deep_merge(prof, extra)
    prof["updated"] = now
    prof_path.parent.mkdir(parents=True, exist_ok=True)
    prof_path.write_text(json.dumps(prof, indent=2) + "\n")
    return prof_path


# ---------------------------------------------------------------- house style
def _profile_arg(value):
    if value:
        return Path(value).expanduser()
    p = need_home()
    return Path(p["profile"])


def _load_profile(path):
    if not path.exists():
        die(f"No style profile at {path}. Run setup first.", 2)
    return json.loads(path.read_text())


def _cards():
    out = {}
    for f in (REPO / "styles" / "cards").glob("*.json"):
        c = json.loads(f.read_text())
        out[c["id"]] = {k: c[k] for k in ("id", "category", "name", "oneliner")}
    return out


def _hits(preset, text):
    return [kw for kw in preset["match"]
            if re.search(r"(?<!\w)" + re.escape(kw.lower()) + r"(e?s)?(?!\w)", text)]


def match_preset(doc, text, wanted=None):
    """Best preset for `text` (most keyword hits, ties -> list order; none -> fallback).
    `wanted` (--type) picks a preset by type name, else is keyword-matched instead of the profile text.
    Returns (preset, how, hits, two alternative types: runner-up matches, then the preset's `near` list)."""
    presets = doc["presets"]
    by_type = {p["type"]: p for p in presets}
    text = (wanted or text).lower()
    ranked = sorted(presets, key=lambda p: -len(_hits(p, text)))  # stable: ties keep list order
    if wanted and wanted.lower() in by_type:
        best, how = by_type[wanted.lower()], "--type"
    elif _hits(ranked[0], text):
        best, how = ranked[0], "--type keywords" if wanted else "keywords"
    else:
        best, how = by_type[doc["fallback"]], "fallback"
    pool = [p for p in ranked if _hits(p, text)] + [by_type[t] for t in best.get("near", []) if t in by_type]
    alts = []
    for p in pool:
        if p is not best and p["type"] not in alts:
            alts.append(p["type"])
    return best, how, (_hits(best, text) if how != "fallback" else []), alts[:2]


def cmd_house_style(args):
    ap = argparse.ArgumentParser(prog="rr.py house-style")
    ap.add_argument("--profile")
    ap.add_argument("--type", dest="type_")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(args)
    prof_path = _profile_arg(a.profile)
    prof = _load_profile(prof_path)
    doc = json.loads((REPO / "styles" / "presets.json").read_text())
    biz = prof.get("business") or {}
    text = f"{biz.get('what_we_do') or ''} {biz.get('name') or ''}"
    preset, how, hits, alts = match_preset(doc, text, a.type_)
    cards = _cards()
    mix = list(preset["default_mix"])
    note = {"keywords": f"Matched '{preset['type']}' from: {', '.join(hits)}.",
            "--type": f"Using '{preset['type']}' (asked for by type).",
            "--type keywords": f"Matched '{preset['type']}' from the type you gave: {', '.join(hits)}.",
            "fallback": f"No business-type words matched, so I used '{preset['type']}' as a neutral start."}[how]
    own_c = (prof.get("captions") or {}).get("card")
    if own_c in cards and cards[own_c]["category"] == "captions":
        old_c = next(i for i in mix if cards[i]["category"] == "captions")
        if old_c != own_c:
            mix[mix.index(old_c)] = own_c
            note += f" Kept your caption card {own_c} instead of {old_c}."
    out = {**preset, "default_mix": mix, "matched_by": how, "matched_words": hits, "note": note,
           "alternatives": alts,
           "cards": [cards[i] for i in mix], "signature_cards": [cards[i] for i in preset["signature"]]}
    if a.apply:
        hs_old = prof.get("house_style") or {}
        extra = {"house_style": {"preset": preset["type"], "signature": preset["signature"], "rotate": True,
                                 "chosen_at": _dt.datetime.now().isoformat(timespec="seconds")}}
        if hs_old.get("preset") != preset["type"]:
            extra["house_style"]["last_signature"] = None
        if prof.get("default_mix") and not a.force:
            out["note"] += " Kept your existing default_mix (use --force to replace it)."
        else:
            extra["default_mix"] = mix
        merge_profile(prof_path, extra)
        out["applied"] = str(prof_path)
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_next_signature(args):
    ap = argparse.ArgumentParser(prog="rr.py next-signature")
    ap.add_argument("--profile")
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args(args)
    prof_path = _profile_arg(a.profile)
    hs = _load_profile(prof_path).get("house_style") or {}
    sig = hs.get("signature") or []
    if not sig:
        return
    last = hs.get("last_signature")
    if not hs.get("rotate") or last not in sig:
        nxt = sig[0]
    else:
        nxt = sig[(sig.index(last) + 1) % len(sig)]
    if a.commit and hs.get("rotate"):
        merge_profile(prof_path, {"house_style": {"last_signature": nxt}})
    print(nxt)


def cmd_palette(args):
    if not args:
        die("usage: rr.py palette <image> [--n 5]")
    n = int(args[args.index("--n") + 1]) if "--n" in args else 5
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", args[0], "-vf", "scale=96:96:force_original_aspect_ratio=decrease",
         "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
        capture_output=True).stdout
    if not raw:
        die("Could not read that image (ffmpeg needed).")
    buckets = {}
    for i in range(0, len(raw) - 3, 4):
        r, g, b, a = raw[i], raw[i + 1], raw[i + 2], raw[i + 3]
        if a < 128:
            continue
        key = (r // 24, g // 24, b // 24)
        acc = buckets.setdefault(key, [0, 0, 0, 0])
        acc[0] += r; acc[1] += g; acc[2] += b; acc[3] += 1
    colors = []
    for acc in sorted(buckets.values(), key=lambda a: -a[3]):
        c = (acc[0] // acc[3], acc[1] // acc[3], acc[2] // acc[3])
        if all(sum((x - y) ** 2 for x, y in zip(c, o)) > 2500 for o, _ in colors):
            colors.append((c, acc[3]))
        if len(colors) >= n:
            break
    total = sum(w for _, w in colors) or 1
    print(json.dumps([{"hex": "#%02X%02X%02X" % c, "share": round(w / total, 2)} for c, w in colors], indent=2))


def cmd_duck_filter(args):
    """Music gain automation from word timings: -18 dB under speech, -8 dB in gaps, 0.25 s ramps."""
    if not args:
        die("usage: rr.py duck-filter <transcript.json> [--duration S]")
    data = json.loads(Path(args[0]).read_text())
    words = data if isinstance(data, list) else data.get("words", [])
    dur = float(args[args.index("--duration") + 1]) if "--duration" in args else None
    spans = []
    for w in words:
        a, b = float(w["start"]), float(w["end"])
        if spans and a - spans[-1][1] < 0.6:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    R = 0.25
    terms = "+".join(
        f"clip((t-({a - 0.1 - R:.2f}))/{R},0,1)*clip(({b + 0.1 + R:.2f}-t)/{R},0,1)" for a, b in spans) or "0"
    f = f"volume='pow(10,(-8-10*min(1,{terms}))/20)':eval=frame"
    f += ",afade=t=in:d=0.5"
    if dur:
        f += f",afade=t=out:st={max(dur - 1.5, 0):.2f}:d=1.5"
    print(f)


def _words_path(mp4):
    return Path(str(Path(mp4).with_suffix("")) + ".words.json")


def cmd_join_drafts(args):
    """Join render_cut drafts in order: <out>.mp4 + <out>.words.json (words shifted by each draft's start)."""
    if len(args) < 3:
        die("usage: rr.py join-drafts <out.mp4> <draft_01.mp4> <draft_02.mp4> [...]")
    out, drafts = Path(args[0]), [Path(a) for a in args[1:]]
    for d in drafts:
        if not d.exists():
            die(f"error: draft not found: {d}")
    lst = out.with_name(out.stem + ".concat.txt")
    lst.write_text("".join("file '%s'\n" % str(d.resolve()).replace("'", "'\\''") for d in drafts))
    code = subprocess.call(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c", "copy", "-movflags", "+faststart", str(out)])
    lst.unlink(missing_ok=True)
    if code != 0:
        die("error: ffmpeg could not join the drafts (were they all made by render_cut.py with the same --aspect "
            "and --fps?)")
    words, offset = [], 0.0
    for d in drafts:
        wp = _words_path(d)
        if wp.exists():
            for w in json.loads(wp.read_text()).get("words", []):
                words.append({**w, "start": round(w["start"] + offset, 3), "end": round(w["end"] + offset, 3)})
        dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                              str(d)], capture_output=True, text=True).stdout.strip()
        offset += float(dur or 0)
    _words_path(out).write_text(json.dumps({"source": str(out), "words": words}, indent=1, ensure_ascii=False))
    print(json.dumps({"out": str(out), "words": str(_words_path(out)), "drafts": len(drafts),
                      "duration": round(offset, 3), "word_count": len(words)}))


COMMANDS = {
    "where": cmd_where, "newest": cmd_newest, "export-dir": cmd_export_dir, "run": cmd_run,
    "set-key": cmd_set_key, "profile-merge": cmd_profile_merge, "palette": cmd_palette,
    "duck-filter": cmd_duck_filter, "join-drafts": cmd_join_drafts,
    "house-style": cmd_house_style, "next-signature": cmd_next_signature,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(0 if len(sys.argv) < 2 else 1)
    COMMANDS[sys.argv[1]](sys.argv[2:])
