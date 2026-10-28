#!/usr/bin/env python3
"""ReelReady doctor: check every dependency, print a table, exit non-zero if something required is missing.

  python3 scripts/doctor.py           # table
  python3 scripts/doctor.py --json    # machine-readable
  python3 scripts/doctor.py --fast    # never call npx (cache lookup only)

Exit codes: 0 = ready, 1 = something required is missing (run scripts/setup.sh) or the disk is
nearly full (FAIL under 1.5 GB free, WARN under 3 GB). Stdlib only.
"""
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VENV_PY = REPO / ".venv" / "bin" / "python"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rr  # noqa: E402  (paths + brand helpers)


def run(cmd, timeout=20):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(REPO))
        return p.returncode, (p.stdout or p.stderr).strip()
    except FileNotFoundError:
        return 127, "not found"
    except subprocess.TimeoutExpired:
        return 124, "timed out"


def version_of(binary, args=("--version",)):
    if not shutil.which(binary):
        return None
    code, out = run([binary, *args])
    if code != 0:
        return None
    m = re.search(r"\d+(\.\d+)+", out)
    return m.group(0) if m else out.splitlines()[0][:30]


def major(v):
    try:
        return tuple(int(x) for x in v.split(".")[:2])
    except Exception:
        return (0, 0)


DISK_WARN_GB = 3.0   # below this: WARN (long or 4K edits may run out of room)
DISK_FAIL_GB = 1.5   # below this: FAIL (HyperFrames itself refuses to render under 1 GB free)


def free_space(main_folder=None):
    """Lowest free space (GB, decimal like Finder) across the volumes an edit writes to:
    the temp dir (HyperFrames frames), the main folder (exports + work) and the repo."""
    spots = [Path(tempfile.gettempdir()), REPO]
    if main_folder:
        spots.append(Path(main_folder))
    seen, worst = set(), None
    for spot in spots:
        while not spot.exists() and spot != spot.parent:
            spot = spot.parent
        try:
            dev = os.stat(spot).st_dev
            if dev in seen:
                continue
            seen.add(dev)
            gb = shutil.disk_usage(spot).free / 1e9
        except OSError:
            continue
        if worst is None or gb < worst[0]:
            worst = (gb, spot)
    return worst


def checks(fast=False):
    res = []

    def add(name, ok, detail, required=True, fix="", status=None):
        st = status or ("ok" if ok else ("missing" if required else "warn"))
        res.append({"name": name, "status": st, "detail": detail, "required": required,
                    "fix": "" if st == "ok" else fix})

    is_mac = platform.system() == "Darwin"
    if is_mac:
        b = shutil.which("brew")
        add("homebrew", bool(b), b or "not installed", required=False,
            fix="Install from https://brew.sh (asks for your Mac password), then re-run setup")

    pyv = platform.python_version()
    add("python3 (system)", major(pyv) >= (3, 9), pyv, fix="brew install python@3.12")

    for binary, fix in [("ffmpeg", "brew install ffmpeg"), ("ffprobe", "comes with ffmpeg")]:
        v = version_of(binary, ("-version",))
        add(binary, bool(v), v or "not found", fix=fix)

    nv = version_of("node")
    add("node >= 18", bool(nv) and major(nv) >= (18, 0), nv or "not found", fix="brew install node")
    add("npx", bool(shutil.which("npx")), shutil.which("npx") or "not found", fix="comes with node")

    uvv = version_of("uv")
    add("uv", bool(uvv), uvv or "not found (pip venv fallback is fine)", required=False, fix="brew install uv")

    if VENV_PY.exists():
        code, out = run([str(VENV_PY), "--version"])
        add(".venv (repo-local python)", code == 0, out, fix="bash scripts/setup.sh")
        code, out = run([str(VENV_PY), "-c", "import faster_whisper; print(faster_whisper.__version__)"])
        add("faster-whisper (local captions)", code == 0, out if code == 0 else "not installed",
            fix="bash scripts/setup.sh")
        req = REPO / "engines" / "requirements.txt"
        if req.exists():
            code, out = run([str(VENV_PY), "-c", "import requests, numpy, PIL; print('ok')"])
            add("engine python packages", code == 0, "installed" if code == 0 else "incomplete",
                fix="bash scripts/setup.sh")
    else:
        add(".venv (repo-local python)", False, "not created", fix="bash scripts/setup.sh")

    yv = version_of(str(REPO / ".venv" / "bin" / "yt-dlp")) or version_of("yt-dlp")
    add("yt-dlp (reference study)", bool(yv), yv or "not found", required=False, fix="bash scripts/setup.sh")

    hf = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    model = hf / "models--Systran--faster-whisper-small"
    add("whisper model (small)", model.exists(), "cached" if model.exists() else "downloads on first use (~480 MB)",
        required=False, fix="bash scripts/setup.sh")

    cached = []
    for pj in (Path.home() / ".npm" / "_npx").glob("*/node_modules/hyperframes/package.json"):
        try:
            cached.append(json.loads(pj.read_text()).get("version", "?"))
        except Exception:
            pass
    if cached:
        best = max(cached, key=lambda v: tuple(int(x) for x in re.findall(r"\d+", v)[:3]))
        add("hyperframes (captions + motion)", True, f"cached v{best}")
    elif fast or not shutil.which("npx"):
        add("hyperframes (captions + motion)", False, "not cached" if shutil.which("npx") else "needs node/npx",
            fix="npx --yes hyperframes --version")
    else:
        code, out = run(["npx", "--no-install", "hyperframes", "--version"], timeout=60)
        add("hyperframes (captions + motion)", code == 0, out.splitlines()[-1][:40] if code == 0 else "not cached",
            fix="npx --yes hyperframes --version")

    engines = [e for e in ["transcribe.py", "cut.py", "render_cut.py", "qa.py"] if not (REPO / "engines" / e).exists()]
    add("engines", not engines, "all present" if not engines else "missing: " + ", ".join(engines),
        fix="re-download the kit")
    cards = list((REPO / "styles" / "cards").glob("*.json")) if (REPO / "styles" / "cards").exists() else []
    add("style cards", bool(cards), f"{len(cards)} cards", required=False, fix="re-download the kit")

    p = rr.paths()
    disk = free_space(p.get("main_folder"))
    if disk:
        gb, spot = disk
        st = "fail" if gb < DISK_FAIL_GB else ("warn" if gb < DISK_WARN_GB else "ok")
        add("free disk space", st == "ok", f"{gb:.1f} GB free on {spot}", required=st == "fail",
            fix=f"free up space (aim for {DISK_WARN_GB:.0f} GB+): empty the Trash, delete old videos or "
                f"<main folder>/.reelready/work/*. Video renders need at least {DISK_FAIL_GB} GB",
            status=st)
    add("main folder", bool(p.get("configured")), p.get("main_folder") or "not set up", required=False,
        fix='say "set up reelready"')
    add("style profile", bool(p.get("profile_exists")), "found" if p.get("profile_exists") else "not yet",
        required=False, fix='say "set up reelready"')
    return res


def main():
    fast = "--fast" in sys.argv
    res = checks(fast)
    ready = all(r["status"] == "ok" for r in res if r["required"])
    if "--json" in sys.argv:
        print(json.dumps({"ready": ready, "checks": res}, indent=2))
        sys.exit(0 if ready else 1)
    b = rr.config().get("brand", {})
    print(f"\n{b.get('name', 'ReelReady')} doctor ({b.get('by', '')})\n")
    w = max(len(r["name"]) for r in res) + 2
    mark = {"ok": "OK  ", "missing": "MISS", "warn": "WARN", "fail": "FAIL"}
    for r in res:
        line = f"  {mark[r['status']]}  {r['name']:<{w}} {r['detail']}"
        if r["fix"]:
            line += f"   -> {r['fix']}"
        print(line)
    print()
    if ready:
        print("Ready. Required pieces are all here." + (" (WARN lines are optional.)" if any(
            r["status"] == "warn" for r in res) else ""))
    else:
        if any(r["status"] == "missing" for r in res):
            print("Not ready yet. Fix: bash scripts/setup.sh   (Claude can run it for you)")
        if any(r["status"] == "fail" for r in res):
            print("Not enough free disk space to render video. Free some space, then run doctor again.")
    sys.exit(0 if ready else 1)


if __name__ == "__main__":
    main()
