#!/usr/bin/env python3
"""Make ReelReady's sound-effect library from scratch: no downloads, no third-party samples.

    python3 engines/make_sfx.py [--out DIR] [--engines-dir DIR] [--keep-wav]

Every effect is synthesised here (noise, sines, filters, envelopes) with a fixed seed, so the
same command gives the same bytes on every machine. Output is 48 kHz mono MP3 (via ffmpeg's
libmp3lame) into the media-use skill's bundled library, plus the subset `engines/sound.py` uses
copied into `engines/sfx/`. `manifest.json` durations are refreshed from the rendered files.

The files are MIT like the rest of the kit (see engines/sfx/ATTRIBUTION.md). Stdlib + ffmpeg only.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

SR = 48000
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
LIB = ROOT / ".claude" / "skills" / "media-use" / "audio" / "assets" / "sfx"
ENGINE_SET = ["whoosh", "whoosh-short", "whoosh-cinematic", "pop", "click-soft", "sparkle",
              "riser", "impact-bass-1", "impact-bass-2"]

# ----------------------------------------------------------------------------- building blocks

def n_of(seconds: float) -> int:
    return int(round(seconds * SR))


def silence(n: int) -> list[float]:
    return [0.0] * n


def noise(n: int, rng: random.Random) -> list[float]:
    return [rng.uniform(-1.0, 1.0) for _ in range(n)]


def sine(n: int, freq, amp=1.0, phase=0.0) -> list[float]:
    """freq and amp may be numbers or functions of time (seconds)."""
    out, ph = [0.0] * n, phase
    fcall, acall = callable(freq), callable(amp)
    for i in range(n):
        t = i / SR
        f = freq(t) if fcall else freq
        a = amp(t) if acall else amp
        out[i] = a * math.sin(ph)
        ph += 2 * math.pi * f / SR
    return out


def glide(f0: float, f1: float, secs: float):
    """Exponential pitch glide from f0 to f1 over secs, then holds f1."""
    r = math.log(f1 / f0)
    return lambda t: f0 * math.exp(r * min(1.0, t / secs))


def exp_decay(n: int, tau: float, start: float = 0.0) -> list[float]:
    return [0.0 if i / SR < start else math.exp(-(i / SR - start) / tau) for i in range(n)]


def ramp(n: int, shape: float = 1.0) -> list[float]:
    """0 -> 1 over n samples; shape > 1 bends it late (slow start, fast finish)."""
    return [(i / max(1, n - 1)) ** shape for i in range(n)]


def hump(n: int, peak_at: float) -> list[float]:
    """Smooth rise to 1 at fraction peak_at of the length, then smooth fall to 0."""
    out, p = [0.0] * n, max(1, int(n * peak_at))
    for i in range(n):
        x = i / p if i < p else (i - p) / max(1, n - p)
        out[i] = math.sin(math.pi / 2 * x) ** 2 if i < p else math.cos(math.pi / 2 * x) ** 2
    return out


def fade(sig: list[float], fin: float = 0.0, fout: float = 0.0) -> list[float]:
    n, a, b = len(sig), n_of(fin), n_of(fout)
    out = list(sig)
    for i in range(min(a, n)):
        out[i] *= i / a
    for i in range(min(b, n)):
        out[n - 1 - i] *= i / b
    return out


def mul(a: list[float], b) -> list[float]:
    if isinstance(b, (int, float)):
        return [x * b for x in a]
    return [x * y for x, y in zip(a, b)]


def mix(*parts, length: int | None = None) -> list[float]:
    """Sum (signal, offset_seconds, gain) tuples or bare signals."""
    norm = [(p, 0.0, 1.0) if isinstance(p, list) else p for p in parts]
    length = length or max(len(s) + n_of(o) for s, o, _ in norm)
    out = [0.0] * length
    for s, off, g in norm:
        k = n_of(off)
        for i, x in enumerate(s):
            if k + i < length:
                out[k + i] += x * g
    return out


def svf(sig: list[float], fc, damping: float = 0.5, mode: str = "band") -> list[float]:
    """Chamberlin state-variable filter; fc may be a function of time. damping = 1/Q."""
    out, low, band = [0.0] * len(sig), 0.0, 0.0
    fcall = callable(fc)
    for i, x in enumerate(sig):
        f = fc(i / SR) if fcall else fc
        f = 2 * math.sin(math.pi * min(f, 7000.0) / SR)
        low += f * band
        high = x - low - damping * band
        band += f * high
        out[i] = band if mode == "band" else low if mode == "low" else high
    return out


def lowpass(sig: list[float], fc: float) -> list[float]:
    a, out, y = math.exp(-2 * math.pi * fc / SR), [0.0] * len(sig), 0.0
    for i, x in enumerate(sig):
        y = (1 - a) * x + a * y
        out[i] = y
    return out


def highpass(sig: list[float], fc: float) -> list[float]:
    return [x - y for x, y in zip(sig, lowpass(sig, fc))]


def soft(sig: list[float], drive: float = 1.0) -> list[float]:
    return [math.tanh(x * drive) for x in sig]


def reverb(sig: list[float], wet: float = 0.3, size: float = 1.0, tail: float = 0.6) -> list[float]:
    """Three feedback combs + a one-pole damp: a small, dark room. Adds `tail` seconds."""
    out = list(sig) + [0.0] * n_of(tail)
    combs = [(0.0297 * size, 0.77), (0.0371 * size, 0.74), (0.0411 * size, 0.72)]
    acc = [0.0] * len(out)
    for d, g in combs:
        k, buf, lp = n_of(d), [0.0] * len(out), 0.0
        for i in range(len(out)):
            prev = buf[i - k] if i >= k else 0.0
            lp = 0.6 * lp + 0.4 * prev
            buf[i] = out[i] + g * lp
            acc[i] += buf[i] / len(combs)
    return [d * (1 - wet) + w * wet for d, w in zip(out, acc)]


def bitcrush(sig: list[float], bits: int, hold: int) -> list[float]:
    q, out, last = 2 ** (bits - 1), [0.0] * len(sig), 0.0
    for i, x in enumerate(sig):
        if i % hold == 0:
            last = round(x * q) / q
        out[i] = last
    return out


def normalize(sig: list[float], peak_db: float = -3.0) -> list[float]:
    pk = max(1e-9, max(abs(x) for x in sig))
    g = 10 ** (peak_db / 20) / pk
    return [max(-1.0, min(1.0, x * g)) for x in sig]


# ----------------------------------------------------------------------------- the recipes
# Each returns a float signal in [-1, 1]. Names and intent match manifest.json.

def whoosh(rng):
    n = n_of(0.6)
    fc = lambda t: 400 + 3600 * math.sin(math.pi * min(1.0, t / 0.6)) ** 1.5
    body = svf(noise(n, rng), fc, damping=0.35)
    return mul(body, hump(n, 0.45))


def whoosh_short(rng):
    n = n_of(0.3)
    fc = lambda t: 600 + 4400 * math.sin(math.pi * min(1.0, t / 0.3)) ** 1.5
    return mul(svf(noise(n, rng), fc, damping=0.35), hump(n, 0.4))


def whoosh_cinematic(rng):
    n, hit = n_of(2.4), 1.6
    sweep = svf(noise(n, rng), lambda t: 150 + 2400 * (min(1.0, t / hit)) ** 2, damping=0.6)
    air = mul(sweep, [min(1.0, (i / SR / hit)) ** 2.2 if i / SR < hit else
                      math.exp(-(i / SR - hit) / 0.35) for i in range(n)])
    rumble = sine(n, 48.0, amp=lambda t: 0.6 * (min(1.0, t / hit) ** 3 if t < hit else math.exp(-(t - hit) / 0.5)))
    thump = mul(sine(n_of(0.5), glide(140, 45, 0.12)), exp_decay(n_of(0.5), 0.18))
    out = mix((air, 0.0, 0.9), (rumble, 0.0, 1.0), (thump, hit - 0.01, 0.8), length=n)
    return reverb(soft(out, 1.4), wet=0.35, size=1.3, tail=0.5)


def pop(rng):
    n = n_of(0.18)
    tone = mul(sine(n, glide(1100, 250, 0.08)), exp_decay(n, 0.035))
    click = mul(lowpass(noise(n_of(0.004), rng), 6000), exp_decay(n_of(0.004), 0.002))
    return mix((tone, 0.0, 1.0), (click, 0.0, 0.5), length=n)


def click_soft(rng):
    n = n_of(0.08)
    return mul(lowpass(noise(n, rng), 2500), exp_decay(n, 0.010))


def click(rng):
    n = n_of(0.06)
    burst = mul(highpass(noise(n, rng), 1500), exp_decay(n, 0.006))
    ring = mul(sine(n, 2600.0), exp_decay(n, 0.009))
    return mix((burst, 0.0, 0.8), (ring, 0.0, 0.6), length=n)


def sparkle(rng):
    n = n_of(1.2)
    parts = []
    for _ in range(9):
        f, at = rng.uniform(2400, 8000), rng.uniform(0.0, 0.5)
        m = n_of(0.5)
        vib = lambda t, f=f: f * (1 + 0.004 * math.sin(2 * math.pi * 7 * t))
        parts.append((mul(sine(m, vib), exp_decay(m, 0.12)), at, rng.uniform(0.35, 0.7)))
    shimmer = mul(highpass(noise(n, rng), 6000), hump(n, 0.3))
    parts.append((shimmer, 0.0, 0.08))
    return mix(*parts, length=n)


def riser(rng):
    secs, n = 4.0, n_of(4.0)
    air = svf(noise(n, rng), lambda t: 150 * (6000 / 150) ** (t / secs), damping=0.5)
    air = mul(air, [((i / n) ** 2.5) for i in range(n)])
    trem = lambda t: 0.5 + 0.5 * math.sin(2 * math.pi * (4 + 12 * (t / secs)) * t)
    tone = sine(n, glide(80, 640, secs), amp=lambda t: 0.5 * (t / secs) ** 1.5 * (0.5 + 0.5 * trem(t)))
    out = mix((air, 0.0, 1.0), (tone, 0.0, 1.0), length=n)
    return fade(soft(out, 1.3), fin=0.05, fout=0.02)


def impact_bass_1(rng):
    n = n_of(0.9)
    body = mul(sine(n, glide(150, 45, 0.15)), exp_decay(n, 0.22))
    snap = mul(lowpass(noise(n_of(0.03), rng), 2000), exp_decay(n_of(0.03), 0.008))
    out = mix((body, 0.0, 1.0), (snap, 0.0, 0.7), length=n)
    return reverb(soft(out, 1.6), wet=0.2, size=0.9, tail=0.3)


def impact_bass_2(rng):
    n, hit = n_of(1.4), 0.25
    swell = mul(svf(noise(n_of(hit), rng), 900, damping=0.7), ramp(n_of(hit), 3.0))
    body = mul(sine(n_of(1.1), glide(130, 38, 0.18)), exp_decay(n_of(1.1), 0.38))
    sub = mul(sine(n_of(1.1), 35.0), exp_decay(n_of(1.1), 0.5))
    snap = mul(lowpass(noise(n_of(0.03), rng), 1800), exp_decay(n_of(0.03), 0.009))
    out = mix((swell, 0.0, 0.5), (body, hit, 1.0), (sub, hit, 0.6), (snap, hit, 0.7), length=n)
    return reverb(soft(out, 1.8), wet=0.25, size=1.2, tail=0.4)


def bell(freq: float, secs: float, bright: float = 1.0) -> list[float]:
    n = n_of(secs)
    partials = [(1.0, 1.0, 0.45), (2.0, 0.45 * bright, 0.25), (2.76, 0.3 * bright, 0.18), (4.07, 0.15 * bright, 0.12)]
    out = mix(*[(mul(sine(n, freq * r), exp_decay(n, tau)), 0.0, a) for r, a, tau in partials], length=n)
    return fade(out, fin=0.004)


def chime(rng):
    n = n_of(1.6)
    return mix((bell(659.3, 1.4), 0.0, 1.0), (bell(784.0, 1.3), 0.26, 0.9), length=n)


def error(rng):
    n, half = n_of(0.6), 0.27
    buzz = lambda f, s: fade(soft(sine(n_of(s), f), 3.0), fin=0.005, fout=0.02)
    return mix((buzz(330.0, half), 0.0, 0.8), (buzz(220.0, half), half + 0.03, 0.8), length=n)


def glitch(rng, secs: float, chunks: int, bits: int, level_lp: float | None, harsh: float):
    n = n_of(secs)
    base = mix((noise(n, rng), 0.0, 0.6), (soft(sine(n, 1000.0 * rng.uniform(0.7, 1.4)), 2.5), 0.0, 0.4), length=n)
    gate = [0.0] * n
    for _ in range(chunks):
        a = rng.uniform(0, secs * 0.85)
        b = min(secs, a + rng.uniform(0.02, 0.07))
        for i in range(n_of(a), n_of(b)):
            gate[i] = 1.0
    out = mul(base, gate)
    out = bitcrush(out, bits, hold=rng.randint(3, 9))
    out = mul(out, [1.0 - 0.6 * (i / n) for i in range(n)])  # front-loaded
    if level_lp:
        out = lowpass(out, level_lp)
    return soft(out, 1.0 + harsh)


def glitch_1(rng):
    return glitch(rng, 0.45, 9, 6, None, 0.6)


def glitch_2(rng):
    return glitch(rng, 0.8, 16, 4, None, 1.4)


def glitch_3(rng):
    return glitch(rng, 0.6, 6, 8, 2500, 0.0)


def notification(rng):
    n = n_of(0.9)
    tone = lambda f, s: fade(mix((sine(n_of(s), f), 0.0, 1.0), (sine(n_of(s), 2 * f), 0.0, 0.2), length=n_of(s)), fin=0.005)
    a = mul(tone(1046.5, 0.7), exp_decay(n_of(0.7), 0.22))
    b = mul(tone(1318.5, 0.7), exp_decay(n_of(0.7), 0.26))
    return mix((a, 0.0, 0.9), (b, 0.18, 1.0), length=n)


def ping(rng):
    n = n_of(0.7)
    tone = mix((sine(n, 2200.0), 0.0, 1.0), (sine(n, 4400.0), 0.0, 0.3), (sine(n, 6600.0), 0.0, 0.1), length=n)
    body = mul(fade(tone, fin=0.002), exp_decay(n, 0.11))
    tick = mul(highpass(noise(n_of(0.005), rng), 3000), exp_decay(n_of(0.005), 0.002))
    return mix((body, 0.0, 1.0), (tick, 0.0, 0.4), length=n)


def key_press(rng, pitch: float = 1.0):
    n = n_of(0.09)
    clack = mul(svf(noise(n, rng), 2600 * pitch, damping=0.8), exp_decay(n, 0.012))
    thock = mul(sine(n, 180.0 * pitch), exp_decay(n, 0.02))
    return mix((clack, 0.0, 0.8), (thock, 0.0, 0.5), length=n)


def typing(rng):
    n, parts, t = n_of(1.5), [], 0.02
    while t < 1.38:
        parts.append((key_press(rng, rng.uniform(0.85, 1.2)), t, rng.uniform(0.6, 1.0)))
        t += rng.uniform(0.06, 0.15)
    return mix(*parts, length=n)


RECIPES = {
    "whoosh": (whoosh, -3.0), "whoosh-short": (whoosh_short, -3.0), "whoosh-cinematic": (whoosh_cinematic, -3.0),
    "pop": (pop, -3.0), "click-soft": (click_soft, -8.0), "click": (click, -4.0),
    "sparkle": (sparkle, -4.0), "riser": (riser, -3.0),
    "impact-bass-1": (impact_bass_1, -3.0), "impact-bass-2": (impact_bass_2, -3.0),
    "chime": (chime, -4.0), "error": (error, -5.0),
    "glitch-1": (glitch_1, -4.0), "glitch-2": (glitch_2, -3.0), "glitch-3": (glitch_3, -9.0),
    "notification": (notification, -4.0), "ping": (ping, -4.0),
    "typing": (typing, -5.0), "key-press": (key_press, -5.0),
}

# ----------------------------------------------------------------------------- output

def write_wav(path: Path, sig: list[float]) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(x * 32767)) for x in sig))


def to_mp3(wav: Path, mp3: Path) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(wav),
                    "-codec:a", "libmp3lame", "-b:a", "192k", "-ar", str(SR), "-ac", "1",
                    "-id3v2_version", "0", "-write_xing", "1", str(mp3)], check=True)


def duration(path: Path) -> float:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return round(float(p.stdout.strip()), 2)


def main() -> int:
    ap = argparse.ArgumentParser(description="Synthesise the bundled SFX library (deterministic, stdlib + ffmpeg).")
    ap.add_argument("--out", type=Path, default=LIB, help="media-use library folder (default: the bundled one)")
    ap.add_argument("--engines-dir", type=Path, default=HERE / "sfx", help="where sound.py's subset is copied")
    ap.add_argument("--only", nargs="*", help="render only these names")
    ap.add_argument("--keep-wav", action="store_true", help="also leave the .wav next to each .mp3")
    a = ap.parse_args()
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        print("make_sfx: ffmpeg + ffprobe are required (brew install ffmpeg)", file=sys.stderr)
        return 1
    a.out.mkdir(parents=True, exist_ok=True)
    a.engines_dir.mkdir(parents=True, exist_ok=True)
    names = a.only or list(RECIPES)
    durations = {}
    with tempfile.TemporaryDirectory() as td:
        for name in names:
            fn, peak_db = RECIPES[name]
            rng = random.Random(f"reelready-sfx:{name}")
            sig = normalize(fn(rng), peak_db)
            wav = Path(td) / f"{name}.wav"
            write_wav(wav, sig)
            mp3 = a.out / f"{name}.mp3"
            to_mp3(wav, mp3)
            if a.keep_wav:
                shutil.copy2(wav, a.out / wav.name)
            durations[name] = duration(mp3)
            if name in ENGINE_SET:
                shutil.copy2(mp3, a.engines_dir / mp3.name)
            print(f"{name:18s} {durations[name]:5.2f} s  {mp3.stat().st_size // 1024:4d} KB")
    manifest = a.out / "manifest.json"
    if manifest.exists():
        data = json.loads(manifest.read_text())
        for name, d in durations.items():
            if name in data:
                data[name]["duration"] = d
        manifest.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        print(f"manifest durations updated: {manifest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
