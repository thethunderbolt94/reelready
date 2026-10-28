"""Shared ffmpeg/ffprobe helpers for the ReelReady engines. Standard library only."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys


def need(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        sys.exit(f"error: '{binary}' not found on PATH. Install ffmpeg (macOS: brew install ffmpeg).")
    return path


def run(cmd: list[str], quiet: bool = True) -> subprocess.CompletedProcess:
    """Run a command; raise with the tail of stderr on failure."""
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        tail = "\n".join((p.stderr or "").strip().splitlines()[-15:])
        raise RuntimeError(f"command failed ({cmd[0]}): {tail}")
    return p


def probe(path: str) -> dict:
    need("ffprobe")
    p = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    return json.loads(p.stdout)


def video_info(path: str) -> dict:
    """Return duration, width, height, fps, rotation-aware display size, has_audio."""
    d = probe(path)
    v = next((s for s in d.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in d.get("streams", []) if s.get("codec_type") == "audio"), None)
    dur = float(d.get("format", {}).get("duration") or (v or {}).get("duration") or 0)
    info = {"duration": round(dur, 3), "has_audio": a is not None, "width": 0, "height": 0, "fps": 0.0}
    if v:
        w, h = int(v.get("width", 0)), int(v.get("height", 0))
        rot = 0
        for sd in v.get("side_data_list", []) or []:
            if "rotation" in sd:
                rot = int(float(sd["rotation"]))
        if "rotate" in (v.get("tags") or {}):
            rot = int(float(v["tags"]["rotate"]))
        if abs(rot) % 180 == 90:
            w, h = h, w
        num, _, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1").partition("/")
        try:
            fps = float(num) / float(den or 1)
        except (ValueError, ZeroDivisionError):
            fps = 0.0
        info.update(width=w, height=h, fps=round(fps, 3))
    return info
