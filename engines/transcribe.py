#!/usr/bin/env python3
"""ReelReady transcription engine — word-level timestamps from a clip.

    python3 engines/transcribe.py <clip> --out transcript.json
        [--backend whisper-local|assemblyai|elevenlabs] [--model small]
        [--language en] [--env <main folder>/.reelready/.env]

Output (all backends):
    {"backend": "...", "language": "en",
     "words":    [{"w": "Hi,", "start": 0.12, "end": 0.40}, ...],
     "segments": [{"text": "Hi, I'm the owner.", "start": 0.12, "end": 1.9}, ...]}

Backends
    whisper-local  (default, free, no key) faster-whisper on CPU int8. The model downloads once
                   to ~/.cache/huggingface (small ~ 480 MB). Prompted to keep fillers verbatim.
    assemblyai     needs ASSEMBLYAI_API_KEY. Upload + poll, disfluencies kept.
    elevenlabs     needs ELEVENLABS_API_KEY. ElevenLabs Scribe.

Keys come from --env <file> if given, else from the process environment. Keys are never printed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.dont_write_bytecode = True  # keep engines/ free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _media import need  # noqa: E402

# Biasing prompt: Whisper silently drops disfluencies unless the context shows them. Captions must be
# verbatim and the cut engine needs to SEE fillers to remove them, so we prime it with a few.
VERBATIM_PROMPT = "Um, so, uh, I mean, like, you know, we, um, we open at, uh, nine."

KEY_NAMES = {"assemblyai": "ASSEMBLYAI_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def load_env_file(path: str | None) -> dict:
    env: dict[str, str] = {}
    if not path:
        return env
    p = Path(path).expanduser()
    if not p.exists():
        die(f"--env file not found: {p}")
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        env[k] = v.strip().strip('"').strip("'")
    return env


def get_key(backend: str, env_path: str | None) -> str:
    name = KEY_NAMES[backend]
    key = load_env_file(env_path).get(name) or os.environ.get(name, "")
    if not key:
        die(f"the '{backend}' backend needs {name}, which is not set "
            f"({'in ' + env_path if env_path else 'in the environment'}). "
            "Use the free local backend instead:  --backend whisper-local")
    return key


def extract_audio(clip: str, dest: str) -> None:
    need("ffmpeg")
    p = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", clip, "-vn", "-ac", "1", "-ar", "16000",
                        "-c:a", "pcm_s16le", dest], capture_output=True, text=True)
    if p.returncode != 0:
        die(f"could not read audio from {clip}: {p.stderr.strip()[-300:]}")


def segments_from_words(words: list[dict], max_gap: float = 0.8) -> list[dict]:
    """Group words into sentence-ish segments: break on . ? ! or a pause > max_gap."""
    segs, cur = [], []
    for i, w in enumerate(words):
        if cur and w["start"] - cur[-1]["end"] > max_gap:
            segs.append(cur); cur = []
        cur.append(w)
        if re.search(r"[.?!]['\"]?$", w["w"]):
            segs.append(cur); cur = []
    if cur:
        segs.append(cur)
    return [{"text": " ".join(x["w"] for x in s).strip(), "start": s[0]["start"], "end": s[-1]["end"]}
            for s in segs]


# ---------------------------------------------------------------- whisper-local
def whisper_local(clip: str, model: str, language: str | None) -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        die("faster-whisper is not installed. Run:  python3 -m pip install -r engines/requirements.txt")
    import wave
    import numpy as np
    # Decode with ffmpeg ourselves (16 kHz mono PCM) instead of faster-whisper's PyAV path:
    # one decoder for every engine, and no PyAV/ffmpeg version mismatches.
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        extract_audio(clip, wav)
        with wave.open(wav, "rb") as wf:
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    wm = WhisperModel(model, device="cpu", compute_type="int8")
    seg_iter, info = wm.transcribe(audio, language=language, word_timestamps=True, beam_size=5,
                                   vad_filter=False, initial_prompt=VERBATIM_PROMPT,
                                   condition_on_previous_text=False)
    words, segments = [], []
    for s in seg_iter:
        for w in (s.words or []):
            t = w.word.strip()
            if t:
                words.append({"w": t, "start": round(w.start, 3), "end": round(w.end, 3)})
        if s.text.strip():
            segments.append({"text": s.text.strip(), "start": round(s.start, 3), "end": round(s.end, 3)})
    # Whisper segments can span several sentences; re-split on punctuation so retake detection works.
    return {"language": info.language, "words": words,
            "segments": segments_from_words(words) if words else segments}


# ---------------------------------------------------------------- assemblyai
def assemblyai(clip: str, key: str, language: str | None) -> dict:
    import requests
    base = "https://api.assemblyai.com/v2"
    h = {"authorization": key}
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        extract_audio(clip, wav)
        with open(wav, "rb") as f:
            r = requests.post(f"{base}/upload", headers=h, data=f, timeout=600)
    if r.status_code != 200:
        die(f"AssemblyAI upload failed ({r.status_code}). Check the key, or use --backend whisper-local.")
    body = {"audio_url": r.json()["upload_url"], "disfluencies": True, "punctuate": True, "format_text": True}
    if language:
        body["language_code"] = language
    else:
        body["language_detection"] = True
    r = requests.post(f"{base}/transcript", headers=h, json=body, timeout=60)
    if r.status_code != 200:
        die(f"AssemblyAI request failed ({r.status_code}): {r.text[:200]}")
    tid = r.json()["id"]
    while True:
        j = requests.get(f"{base}/transcript/{tid}", headers=h, timeout=60).json()
        if j.get("status") == "completed":
            break
        if j.get("status") == "error":
            die(f"AssemblyAI transcription error: {j.get('error')}")
        time.sleep(2)
    words = [{"w": w["text"], "start": round(w["start"] / 1000, 3), "end": round(w["end"] / 1000, 3)}
             for w in j.get("words", [])]
    segs = []
    s = requests.get(f"{base}/transcript/{tid}/sentences", headers=h, timeout=60)
    if s.status_code == 200:
        segs = [{"text": x["text"], "start": round(x["start"] / 1000, 3), "end": round(x["end"] / 1000, 3)}
                for x in s.json().get("sentences", [])]
    return {"language": j.get("language_code") or language or "", "words": words,
            "segments": segs or segments_from_words(words)}


# ---------------------------------------------------------------- elevenlabs
def elevenlabs(clip: str, key: str, language: str | None) -> dict:
    import requests
    data = {"model_id": "scribe_v1", "tag_audio_events": "false", "timestamps_granularity": "word"}
    if language:
        data["language_code"] = language
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "a.wav")
        extract_audio(clip, wav)
        with open(wav, "rb") as f:
            r = requests.post("https://api.elevenlabs.io/v1/speech-to-text", headers={"xi-api-key": key},
                              files={"file": ("a.wav", f, "audio/wav")}, data=data, timeout=1800)
    if r.status_code != 200:
        die(f"ElevenLabs Scribe failed ({r.status_code}). Check the key, or use --backend whisper-local.")
    j = r.json()
    words = [{"w": w["text"].strip(), "start": round(float(w["start"]), 3), "end": round(float(w["end"]), 3)}
             for w in j.get("words", []) if w.get("type", "word") == "word" and w.get("text", "").strip()]
    return {"language": j.get("language_code") or language or "", "words": words,
            "segments": segments_from_words(words)}


def main() -> None:
    ap = argparse.ArgumentParser(description="Word-level transcription (local Whisper by default).")
    ap.add_argument("clip")
    ap.add_argument("--out", required=True)
    ap.add_argument("--backend", default="whisper-local", choices=["whisper-local", "assemblyai", "elevenlabs"])
    ap.add_argument("--model", default="small", help="whisper-local model: tiny|base|small|medium|large-v3")
    ap.add_argument("--language", default=None, help="ISO code, e.g. en. Omit to auto-detect.")
    ap.add_argument("--env", default=None, help="path to a .env file holding optional API keys")
    a = ap.parse_args()
    if not Path(a.clip).exists():
        die(f"clip not found: {a.clip}")

    t0 = time.time()
    if a.backend == "whisper-local":
        res = whisper_local(a.clip, a.model, a.language)
    elif a.backend == "assemblyai":
        res = assemblyai(a.clip, get_key("assemblyai", a.env), a.language)
    else:
        res = elevenlabs(a.clip, get_key("elevenlabs", a.env), a.language)

    out = {"backend": a.backend, **res}
    if a.backend == "whisper-local":
        out["model"] = a.model
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"transcribed {Path(a.clip).name}: {len(out['words'])} words, {len(out['segments'])} segments, "
          f"lang={out['language']} via {a.backend} in {time.time() - t0:.1f}s -> {a.out}")


if __name__ == "__main__":
    main()
