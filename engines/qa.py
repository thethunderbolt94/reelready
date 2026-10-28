#!/usr/bin/env python3
"""ReelReady QA — probe an export, pull frames, print one PASS/FAIL line.

    python3 engines/qa.py <mp4> --frames 6 --out <dir> [--expect 1080x1920] [--min-duration 3]

Writes <dir>/probe.json (duration, width, height, fps, has_audio, loudness from ebur128, checks)
and <dir>/frame_01.jpg .. frame_NN.jpg (512 px wide, evenly spaced). Prints exactly one line that
starts with "QA PASS" or "QA FAIL". Exit code 0 on pass, 1 on fail.

Fails when: resolution != --expect, duration < --min-duration, no audio stream,
or integrated loudness outside -20..-12 LUFS.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # keep engines/ free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _media import need, run, video_info  # noqa: E402

LUFS_MIN, LUFS_MAX = -20.0, -12.0


def loudness(path: str) -> dict:
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-vn",
                        "-filter_complex", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    tail = p.stderr[p.stderr.rfind("Summary:"):] if "Summary:" in p.stderr else ""

    def grab(label: str):
        m = re.search(rf"{label}:\s*(-?[\d.]+|-inf)", tail)
        return None if not m or m.group(1) == "-inf" else float(m.group(1))
    return {"integrated_lufs": grab("I"), "lra_lu": grab("LRA"), "true_peak_dbfs": grab("Peak")}


def main() -> None:
    ap = argparse.ArgumentParser(description="Probe + frames + PASS/FAIL for an exported MP4.")
    ap.add_argument("mp4")
    ap.add_argument("--frames", type=int, default=6)
    ap.add_argument("--out", required=True)
    ap.add_argument("--expect", default="1080x1920", help="expected WxH")
    ap.add_argument("--min-duration", type=float, default=3.0)
    a = ap.parse_args()
    need("ffmpeg")
    if not Path(a.mp4).exists():
        print(f"QA FAIL: file not found: {a.mp4}")
        sys.exit(1)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    info = video_info(a.mp4)
    probe = {"file": str(Path(a.mp4).resolve()), **info}
    probe["audio"] = loudness(a.mp4) if info["has_audio"] else {"integrated_lufs": None}

    frames = []
    n = max(1, a.frames)
    for i in range(n):
        t = info["duration"] * (i + 0.5) / n
        f = out / f"frame_{i + 1:02d}.jpg"
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", a.mp4, "-frames:v", "1",
             "-vf", "scale=512:-2", "-q:v", "3", str(f)])
        frames.append({"file": f.name, "t": round(t, 3)})
    probe["frames"] = frames

    ew, _, eh = a.expect.partition("x")
    lufs = probe["audio"]["integrated_lufs"]
    fails = []
    if (info["width"], info["height"]) != (int(ew), int(eh)):
        fails.append(f"resolution {info['width']}x{info['height']} != {a.expect}")
    if info["duration"] < a.min_duration:
        fails.append(f"duration {info['duration']:.2f}s < {a.min_duration:g}s")
    if not info["has_audio"]:
        fails.append("no audio")
    elif lufs is None or not (LUFS_MIN <= lufs <= LUFS_MAX):
        fails.append(f"loudness {lufs} LUFS outside {LUFS_MIN:g}..{LUFS_MAX:g}")
    probe["pass"] = not fails
    probe["fails"] = fails
    (out / "probe.json").write_text(json.dumps(probe, indent=1))

    summary = (f"{Path(a.mp4).name} {info['width']}x{info['height']} {info['fps']:g}fps "
               f"{info['duration']:.2f}s audio={'yes' if info['has_audio'] else 'no'} "
               f"I={lufs if lufs is not None else 'n/a'} LUFS, {n} frames -> {out}")
    if fails:
        print(f"QA FAIL: {'; '.join(fails)} | {summary}")
        sys.exit(1)
    print(f"QA PASS: {summary}")


if __name__ == "__main__":
    main()
