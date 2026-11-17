#!/usr/bin/env python3
"""ReelReady sorter: put every clip in "raw footage" into a labelled folder, and build the library.

Called by `python3 scripts/rr.py sort [--dry-run] [--undo [BATCH]] [--resort] [--json] [--quiet]`.
Standard library only (it calls ffprobe/ffmpeg, and the repo .venv's faster-whisper only when the
quick sound check is unsure).

Groups (folder names inside raw footage, exactly):
  Talking to camera   video with speech
  B-roll              video, no speech
  Voice notes         audio only
  Photos              images
  Too short           video under 1.5 s

Safety: files are MOVED inside raw footage, never renamed, never deleted, never overwritten. A name
clash leaves the file where it is and reports it. Every move is one line in
<main>/.reelready/sort-log.jsonl ({batch, ts, from, to, reason, size}); `--undo` puts the last batch (or a
named one) back exactly. Writes <main>/.reelready/library.json and thumbnails in
<main>/.reelready/work/library/thumbs/.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GROUPS = ["Talking to camera", "B-roll", "Voice notes", "Photos", "Too short"]
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".3gp", ".hevc"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp", ".gif", ".tif", ".tiff", ".bmp", ".dng", ".avif"}
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".aif", ".aiff", ".caf", ".ogg", ".opus", ".flac", ".amr"}
MEDIA_EXT = VIDEO_EXT | IMAGE_EXT | AUDIO_EXT
TOO_SHORT = 1.5          # seconds: a video under this goes to "Too short"
SPEECH_WINDOW = 20.0     # seconds of sound checked for speech
THUMB_H = 360
LIB_VERSION = 1
WHISPER_MODELS = ["tiny", "tiny.en", "base", "base.en", "small", "small.en"]  # first one already on disk wins

# Homebrew installs land outside a fresh shell's PATH on a new Mac; look there too (same as doctor.py).
for _d in ("/opt/homebrew/bin", "/usr/local/bin"):
    if os.path.isdir(_d) and _d not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + _d


# ---------------------------------------------------------------- paths
class Home:
    def __init__(self, main: Path):
        self.main = Path(main)
        self.raw = self.main / "raw footage"
        self.rr = self.main / ".reelready"
        self.log = self.rr / "sort-log.jsonl"
        self.library = self.rr / "library.json"
        self.status = self.rr / "sort-status.json"
        self.lock = self.rr / "sort.lock"
        self.libdir = self.rr / "work" / "library"
        self.thumbs = self.libdir / "thumbs"
        self.cache = self.libdir / "probe-cache.json"

    def rel(self, p: Path) -> str:
        return Path(p).relative_to(self.main).as_posix()

    def abs(self, rel: str) -> Path:
        return self.main / Path(rel)


def now_iso() -> str:
    return _dt.datetime.now().isoformat(timespec="seconds")


def write_json(path: Path, data) -> None:
    """Write JSON atomically (temp file in the same folder, then rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=str(path.parent))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


# ---------------------------------------------------------------- scanning
def is_media(p: Path) -> bool:
    return p.is_file() and not p.name.startswith(".") and p.suffix.lower() in MEDIA_EXT


def group_of(home: Home, p: Path) -> str | None:
    """The group folder a file sits in directly (raw footage/<Group>/file), else None."""
    rel = p.relative_to(home.raw).parts
    return rel[0] if len(rel) == 2 and rel[0] in GROUPS else None


def scan(home: Home) -> list[Path]:
    if not home.raw.is_dir():
        return []
    return sorted((p for p in home.raw.rglob("*") if is_media(p)), key=lambda p: p.as_posix().lower())


def pending(home: Home, resort: bool = False) -> list[Path]:
    """Media files not yet in a group folder (all files with resort)."""
    return [p for p in scan(home) if resort or group_of(home, p) is None]


def cache_key(p: Path) -> str:
    st = p.stat()
    return f"{p.name}|{st.st_size}|{st.st_mtime_ns}"


# ---------------------------------------------------------------- probing
def run(cmd, timeout=60, text=True):
    return subprocess.run(cmd, capture_output=True, text=text, timeout=timeout)


def _shoot_day(fmt_tags: dict, stream_tags: dict, mtime: float) -> tuple[str, str]:
    tags = {k.lower(): v for k, v in {**stream_tags, **fmt_tags}.items()}
    for key in ("com.apple.quicktime.creationdate", "creation_time", "date"):
        v = tags.get(key)
        if not v:
            continue
        try:
            s = v.strip().replace("Z", "+00:00")
            if len(s) >= 5 and s[-5] in "+-" and s[-3] != ":":   # +0530 -> +05:30
                s = s[:-2] + ":" + s[-2:]
            d = _dt.datetime.fromisoformat(s)
            if d.year < 2000:   # cameras with no clock write 1904/1970
                continue
            if d.tzinfo is not None and key != "com.apple.quicktime.creationdate":
                d = d.astimezone()  # UTC tag -> this computer's local day
            return d.date().isoformat(), key
        except ValueError:
            continue
    return _dt.date.fromtimestamp(mtime).isoformat(), "file date"


def probe(p: Path) -> dict:
    """Kind, duration, display size (rotation-aware), has_audio, shoot day. ok False if ffprobe can't read it."""
    ext = p.suffix.lower()
    st = p.stat()
    info = {"ok": True, "kind": None, "duration": 0.0, "width": 0, "height": 0, "has_audio": False,
            "shoot_day": None, "day_from": None, "size": st.st_size}
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(p)])
    data = None
    if r.returncode == 0:
        try:
            data = json.loads(r.stdout or "{}")
        except ValueError:
            data = None
    if not data or not data.get("streams"):
        info["shoot_day"], info["day_from"] = _dt.date.fromtimestamp(st.st_mtime).isoformat(), "file date"
        if ext in IMAGE_EXT:          # e.g. HEIC on an older ffmpeg: still a photo, just no size/thumbnail
            info["kind"] = "photo"
            return info
        info["ok"] = False
        return info
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    vids = [s for s in streams if s.get("codec_type") == "video"
            and not (s.get("disposition") or {}).get("attached_pic")]
    auds = [s for s in streams if s.get("codec_type") == "audio"]
    v = vids[0] if vids else None
    dur = 0.0
    for cand in (fmt.get("duration"), (v or {}).get("duration"), (auds[0] if auds else {}).get("duration")):
        try:
            dur = float(cand)
            break
        except (TypeError, ValueError):
            continue
    if ext in IMAGE_EXT:
        info["kind"] = "photo"
    elif v is None and auds:
        info["kind"] = "audio"
    elif v is not None:
        nb = (v.get("nb_frames") or "")
        still = v.get("codec_name") in {"mjpeg", "png", "bmp", "tiff", "webp"} and (dur <= 0.05 or nb == "1")
        info["kind"] = "photo" if still else "video"
    else:
        info["ok"] = False
        return info
    if v:
        w, h = int(v.get("width") or 0), int(v.get("height") or 0)
        rot = 0
        for sd in v.get("side_data_list") or []:
            if "rotation" in sd:
                try:
                    rot = int(float(sd["rotation"]))
                except (TypeError, ValueError):
                    pass
        if "rotate" in (v.get("tags") or {}):
            try:
                rot = int(float(v["tags"]["rotate"]))
            except (TypeError, ValueError):
                pass
        if abs(rot) % 180 == 90:
            w, h = h, w
        info["width"], info["height"] = w, h
    info["duration"] = round(dur if info["kind"] != "photo" else 0.0, 3)
    info["has_audio"] = bool(auds)
    info["shoot_day"], info["day_from"] = _shoot_day(fmt.get("tags") or {}, (v or {}).get("tags") or {}, st.st_mtime)
    return info


def orientation(w: int, h: int) -> str | None:
    if not w or not h:
        return None
    r = w / h
    return "square" if 0.9 <= r <= 1.1 else ("portrait" if r < 1 else "landscape")


# ---------------------------------------------------------------- speech: quick sound check
def sound_profile(p: Path, seconds: float = SPEECH_WINDOW) -> dict | None:
    """Loudness and zero-crossing rate per 20 ms over the first `seconds` (ffmpeg astats, so it is fast).
    Speech swings between voiced and hissy sounds (zero-crossing rate varies a lot) and dips between
    syllables; tones, music beds and room noise do not."""
    af = ("aresample=16000,asetnsamples=n=320:p=0,astats=metadata=1:reset=1:measure_overall=none:"
          "measure_perchannel=RMS_level+Zero_crossings_rate,ametadata=mode=print:file=-")
    try:
        r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-t", f"{seconds}", "-i", str(p), "-vn", "-ac", "1",
                            "-af", af, "-f", "null", "-"], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None
    dbs, zcr = [], []
    for line in r.stdout.splitlines():
        if line.startswith("lavfi.astats.1.RMS_level="):
            v = line.split("=", 1)[1]
            try:
                dbs.append(max(-100.0, float(v)))
            except ValueError:
                dbs.append(-100.0)
        elif line.startswith("lavfi.astats.1.Zero_crossings_rate="):
            try:
                zcr.append(float(line.split("=", 1)[1]))
            except ValueError:
                zcr.append(0.0)
    if len(dbs) < 10 or len(zcr) != len(dbs):
        return None
    dbs = [d if d == d else -100.0 for d in dbs]   # nan -> silence
    srt = sorted(dbs)
    pct = lambda q: srt[min(len(srt) - 1, int(q * len(srt)))]  # noqa: E731
    p10, p90, p95 = pct(0.10), pct(0.90), pct(0.95)
    on = [i for i, d in enumerate(dbs) if d > p90 - 25]          # frames with sound in them
    z = [zcr[i] for i in on]
    zmean = sum(z) / len(z) if z else 0.0
    zcv = (sum((x - zmean) ** 2 for x in z) / len(z)) ** 0.5 / zmean if z and zmean else 0.0
    dips = sum(1 for i in range(5, len(dbs) - 5) if dbs[i] > p90 - 25
               and dbs[i] < max(dbs[i - 5:i]) - 8 and dbs[i] < max(dbs[i + 1:i + 6]) - 8)
    secs = len(dbs) * 0.02
    return {"p10": round(p10, 1), "p90": round(p90, 1), "p95": round(p95, 1), "dynamic": round(p90 - p10, 1),
            "active": round(len(on) / len(dbs), 2), "zcr_var": round(zcv, 2),
            "dips_per_s": round(dips / secs, 2), "seconds": round(secs, 1)}


def judge_sound(sp: dict | None) -> tuple[bool | None, str]:
    """(True/False, why) when the sound alone is clear; (None, why) when a speech model should listen."""
    if sp is None:
        return False, "no readable sound"
    if sp["p95"] < -48:
        return False, "silent"
    if sp["dynamic"] < 8:
        return False, "steady sound, no talking pattern"
    if sp["zcr_var"] < 0.3 and sp["dips_per_s"] < 0.3:
        return False, "steady tone or noise, no talking pattern"
    if sp["zcr_var"] >= 0.8 and sp["dips_per_s"] >= 1.5 and 0.15 <= sp["active"] <= 0.85:
        return True, "talking pattern in the sound"
    return None, "unsure from the sound alone"


def heuristic_guess(sp: dict) -> bool:
    return sp.get("zcr_var", 0) >= 0.6 and sp.get("dips_per_s", 0) >= 1.0 and sp.get("active", 1) <= 0.9


def venv_python() -> Path | None:
    for cand in (REPO / ".venv" / "bin" / "python", REPO / ".venv" / "Scripts" / "python.exe"):
        if cand.exists():
            return cand
    return None


def cached_whisper_model() -> str | None:
    hub = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")) / "hub"
    for m in WHISPER_MODELS:
        if (hub / f"models--Systran--faster-whisper-{m}").is_dir():
            return m
    return None


LISTEN_SCRIPT = r"""
import json, sys, wave
import numpy as np
from faster_whisper.vad import VadOptions, get_speech_timestamps
model_name, wavs = sys.argv[1], json.loads(sys.stdin.read())
model, out = None, {}
for w in wavs:
    try:
        with wave.open(w, "rb") as wf:
            audio = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        secs = len(audio) / 16000
        ts = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=300))
        vad = sum(t["end"] - t["start"] for t in ts) / 16000
        r = {"vad_s": round(vad, 1), "secs": round(secs, 1)}
        if vad >= min(3.0, 0.3 * secs):
            r["speech"], r["how"] = True, f"voice detected for {vad:.0f} s"
        elif vad < 0.4:
            r["speech"], r["how"] = False, "no voice detected"
        elif model_name != "-":
            if model is None:
                from faster_whisper import WhisperModel
                model = WhisperModel(model_name, device="cpu", compute_type="int8", local_files_only=True)
            segs, _ = model.transcribe(audio, beam_size=1, vad_filter=True, condition_on_previous_text=False,
                                       without_timestamps=True)
            n = sum(len(s.text.split()) for s in segs if s.no_speech_prob < 0.6)
            r["speech"], r["how"] = n >= 3, f"heard {n} words (whisper {model_name})"
        else:
            r["speech"], r["how"] = vad >= 1.0, f"voice detected for {vad:.1f} s"
        out[w] = r
    except Exception as e:
        out[w] = {"error": str(e)[:200]}
print(json.dumps(out))
"""


def listen(paths: list[Path], workdir: Path) -> dict[str, dict]:
    """faster-whisper's voice detector (and, only when that is unsure, a Whisper model already on disk) on the
    first SPEECH_WINDOW seconds of each file, in one process. Returns {str(path): {"speech": bool, "how": str}};
    empty when the repo .venv is missing (then the sound check's best guess is used). Never downloads."""
    py = venv_python()
    if not paths or py is None:
        return {}
    model = cached_whisper_model() or "-"
    workdir.mkdir(parents=True, exist_ok=True)
    wavs = {}
    for i, p in enumerate(paths):
        wav = workdir / f"listen_{os.getpid()}_{i:04d}.wav"
        r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-t", f"{SPEECH_WINDOW}", "-i", str(p),
                            "-vn", "-ac", "1", "-ar", "16000", str(wav)], capture_output=True, timeout=60)
        if r.returncode == 0:
            wavs[str(wav)] = str(p)
    if not wavs:
        return {}
    try:
        r = subprocess.run([str(py), "-c", LISTEN_SCRIPT, model], input=json.dumps(list(wavs)),
                           capture_output=True, text=True, timeout=90 + 15 * len(wavs))
        res = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 and r.stdout.strip() else {}
    except (subprocess.TimeoutExpired, ValueError, IndexError):
        res = {}
    finally:
        for w in wavs:
            Path(w).unlink(missing_ok=True)
    return {wavs[w]: v for w, v in res.items() if w in wavs and "speech" in v}


# ---------------------------------------------------------------- thumbnails
def make_thumb(p: Path, kind: str, duration: float, out: Path) -> bool:
    if out.exists():
        return True
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(".tmp-" + out.name)
    if kind == "video":
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", f"{max(0.0, duration / 2):.2f}", "-i", str(p),
               "-frames:v", "1", "-vf", f"scale=-2:{THUMB_H}", "-q:v", "5", str(tmp)]
    elif kind == "photo":
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(p), "-frames:v", "1",
               "-vf", f"scale=-2:'min({THUMB_H},ih)'", "-q:v", "5", str(tmp)]
    elif kind == "audio":
        cmd = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-t", "120", "-i", str(p), "-filter_complex",
               f"color=c=0xEFE7D7:s=480x{THUMB_H}[bg];[0:a]aformat=channel_layouts=mono,"
               f"showwavespic=s=440x220:colors=0x151412:scale=sqrt[w];[bg][w]overlay=20:70,format=yuvj420p",
               "-frames:v", "1", "-q:v", "5", str(tmp)]
    else:
        return False
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        tmp.unlink(missing_ok=True)
        return False
    if r.returncode != 0 and kind == "video":   # very short clips: grab the first frame instead
        r = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(p), "-frames:v", "1",
                            "-vf", f"scale=-2:{THUMB_H}", "-q:v", "5", str(tmp)], capture_output=True, timeout=60)
    if r.returncode == 0 and tmp.exists() and tmp.stat().st_size > 0:
        os.replace(tmp, out)
        return True
    tmp.unlink(missing_ok=True)
    return False


# ---------------------------------------------------------------- analysis
def analyze(home: Home, files: list[Path], cache: dict, progress=None) -> dict[str, dict]:
    """Probe + sound check + thumbnail for each file (cached by name|size|mtime). Returns {str(path): rec}."""
    out: dict[str, dict] = {}
    todo = []
    for p in files:
        key = cache_key(p)
        rec = cache.get(key)
        if rec and rec.get("guess") and venv_python():
            rec = None   # last time was a best guess without the speech model; listen properly now
        if rec and (rec.get("thumb") is None or (home.thumbs / rec["thumb"]).exists()):
            out[str(p)] = rec
        else:
            todo.append((p, key))

    def work(item):
        p, key = item
        info = probe(p)
        rec = {**info, "speech": None, "speech_how": None, "sound": None}
        if not info["ok"]:
            rec["thumb"] = None
            return p, key, rec
        if info["kind"] == "video" and info["duration"] >= TOO_SHORT:
            if not info["has_audio"]:
                rec["speech"], rec["speech_how"] = False, "no sound track"
            else:
                sp = sound_profile(p)
                rec["sound"] = sp
                rec["speech"], rec["speech_how"] = judge_sound(sp)
        elif info["kind"] == "audio":
            rec["speech"], rec["speech_how"] = None, "voice note"
        name = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16] + ".jpg"
        rec["thumb"] = name if make_thumb(p, info["kind"], info["duration"], home.thumbs / name) else None
        return p, key, rec

    done = 0
    workers = max(2, min(8, os.cpu_count() or 4))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for p, key, rec in ex.map(work, todo):
            out[str(p)] = rec
            cache[key] = rec
            done += 1
            if progress:
                progress(done, len(todo))

    unsure = [Path(k) for k, r in out.items() if r.get("ok") and r.get("kind") == "video"
              and r.get("duration", 0) >= TOO_SHORT and r.get("speech") is None]
    if unsure:
        heard = listen(unsure, home.libdir / "listen")
        for p in unsure:
            rec = out[str(p)]
            h = heard.get(str(p))
            if h:
                rec["speech"], rec["speech_how"] = bool(h["speech"]), h["how"]
            else:
                rec["speech"] = heuristic_guess(rec["sound"] or {"dynamic": 0, "burst_rate": 0, "active": 1})
                rec["speech_how"] = "best guess from the sound (no speech model on this computer)"
                rec["guess"] = True
            cache[cache_key(p)] = rec
    return out


def classify(rec: dict) -> tuple[str | None, str]:
    """(group, reason in plain words). group None = leave it where it is."""
    if not rec.get("ok"):
        return None, "could not open this file"
    kind, dur = rec.get("kind"), rec.get("duration") or 0
    if kind == "photo":
        return "Photos", "photo"
    if kind == "audio":
        return "Voice notes", f"sound only, {dur:.1f} s"
    if dur < TOO_SHORT:
        return "Too short", f"video, {dur:.1f} s (under {TOO_SHORT} s)"
    if rec.get("speech"):
        return "Talking to camera", f"video, {dur:.1f} s, speech ({rec.get('speech_how')})"
    return "B-roll", f"video, {dur:.1f} s, no speech ({rec.get('speech_how')})"


# ---------------------------------------------------------------- log
def read_log(home: Home) -> list[dict]:
    if not home.log.exists():
        return []
    out = []
    for line in home.log.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def append_log(home: Home, rows: list[dict]) -> None:
    if not rows:
        return
    home.log.parent.mkdir(parents=True, exist_ok=True)
    with open(home.log, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def new_batch_id(home: Home) -> str:
    base = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    used = {r.get("batch") for r in read_log(home)}
    bid, i = base, 2
    while bid in used:
        bid, i = f"{base}-{i}", i + 1
    return bid


def safe_move(src: Path, dst: Path) -> str | None:
    """Move without ever overwriting. Returns None on success, else the reason it was left alone."""
    if dst.exists() or dst.is_symlink():
        return "a file with the same name is already there"
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)          # fails if dst exists: no overwrite even in a race
        os.unlink(src)
        return None
    except FileExistsError:
        return "a file with the same name is already there"
    except OSError:
        pass                       # no hard links on this drive (e.g. exFAT): check-then-rename
    if dst.exists():
        return "a file with the same name is already there"
    try:
        os.rename(src, dst)
        return None
    except OSError as e:
        return f"could not move it ({e.strerror or e})"


# ---------------------------------------------------------------- lock + status
def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def take_lock(home: Home) -> bool:
    home.rr.mkdir(parents=True, exist_ok=True)
    for _ in range(2):
        try:
            fd = os.open(str(home.lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return True
        except FileExistsError:
            try:
                pid = int(home.lock.read_text().strip() or 0)
            except (OSError, ValueError):
                pid = 0
            if pid and _pid_alive(pid):
                return False
            home.lock.unlink(missing_ok=True)   # stale lock from a crashed run
    return False


def release_lock(home: Home) -> None:
    home.lock.unlink(missing_ok=True)


def set_status(home: Home, **kw) -> None:
    write_json(home.status, {"pid": os.getpid(), "updated": now_iso(), **kw})


# ---------------------------------------------------------------- library
def build_library(home: Home, cache: dict, batch: dict | None = None) -> dict:
    files = scan(home)
    recs = analyze(home, files, cache)
    old = read_json(home.library, {}) or {}
    log = read_log(home)
    undone = {r.get("undo_of") for r in log if r.get("undo_of")}
    moved_by = {}   # where each sort put a file -> that batch (undone batches don't count)
    for r in log:
        if not r.get("undo_of") and r.get("batch") not in undone and r.get("to"):
            moved_by[r["to"]] = r["batch"]
    items = []
    for p in files:
        rec = recs.get(str(p)) or {}
        grp, reason = classify(rec)
        here = group_of(home, p)
        key = cache_key(p)
        items.append({
            "id": hashlib.sha1(key.encode("utf-8")).hexdigest()[:12],
            "path": home.rel(p), "name": p.name, "group": grp, "folder": here, "sorted": bool(grp) and here == grp,
            "kind": rec.get("kind"), "duration": rec.get("duration"), "width": rec.get("width"),
            "height": rec.get("height"), "orientation": orientation(rec.get("width") or 0, rec.get("height") or 0),
            "shoot_day": rec.get("shoot_day"), "day_from": rec.get("day_from"), "speech": rec.get("speech"),
            "speech_how": rec.get("speech_how"), "size": rec.get("size"), "reason": reason,
            "thumb": home.rel(home.thumbs / rec["thumb"]) if rec.get("thumb") else None,
            "batch": moved_by.get(home.rel(p)),
        })
    counts = {g: sum(1 for i in items if i["folder"] == g) for g in GROUPS}
    lib = {"version": LIB_VERSION, "updated": now_iso(), "groups": GROUPS, "counts": counts,
           "unsorted": sum(1 for i in items if i["folder"] is None),
           "last_batch": batch if batch is not None else old.get("last_batch"), "items": items}
    write_json(home.library, lib)
    return lib


# ---------------------------------------------------------------- commands
def do_sort(home: Home, dry_run=False, resort=False, quiet=False) -> dict:
    if not home.raw.is_dir():
        return {"ok": False, "error": f'No "raw footage" folder in {home.main}.'}
    if not dry_run and not take_lock(home):
        return {"ok": False, "error": "A sort is already running. Try again in a minute."}
    t0 = time.time()
    try:
        cache = read_json(home.cache, {}) or {}
        todo = pending(home, resort)
        if not dry_run:
            set_status(home, running=True, total=len(todo), done=0, started=now_iso())
        prog = (lambda d, n: set_status(home, running=True, total=n, done=d)) if not dry_run else None
        recs = analyze(home, todo, cache, progress=prog)
        write_json(home.cache, cache)
        batch_id = None if dry_run else new_batch_id(home)
        plan, moved, left, rows = [], [], [], []
        for p in todo:
            rec = recs.get(str(p)) or {}
            grp, reason = classify(rec)
            entry = {"from": home.rel(p), "group": grp, "reason": reason}
            if grp is None:
                left.append({**entry, "why": reason})
                continue
            dst = home.raw / grp / p.name
            if dst == p:
                continue
            entry["to"] = home.rel(dst)
            plan.append(entry)
            if dry_run:
                if dst.exists():
                    left.append({**entry, "why": "a file with the same name is already there"})
                continue
            why = safe_move(p, dst)
            if why:
                left.append({**entry, "why": why})
                continue
            row = {"batch": batch_id, "ts": now_iso(), "from": entry["from"], "to": entry["to"],
                   "reason": reason, "size": rec.get("size")}
            append_log(home, [row])    # one line per move, written as it happens
            rows.append(row)
            moved.append(entry)
        lib = None
        if not dry_run:
            batch = {"id": batch_id, "at": now_iso(), "moved": len(moved),
                     "counts": {g: sum(1 for m in moved if m["group"] == g) for g in GROUPS}} if moved else None
            lib = build_library(home, cache, batch if moved else None)
            write_json(home.cache, cache)
        counts = {g: sum(1 for m in (plan if dry_run else moved) if m["group"] == g) for g in GROUPS}
        return {"ok": True, "dry_run": dry_run, "batch": batch_id if moved else None, "checked": len(todo),
                "moved": len(moved), "planned": plan if dry_run else None, "counts": counts, "left": left,
                "seconds": round(time.time() - t0, 1), "library": str(home.library) if lib else None,
                "total_in_library": len(lib["items"]) if lib else None}
    finally:
        if not dry_run:
            set_status(home, running=False, finished=now_iso())
            release_lock(home)


def batches(home: Home) -> list[str]:
    log = read_log(home)
    undone = {r.get("undo_of") for r in log if r.get("undo_of")}
    order = []
    for r in log:
        b = r.get("batch")
        if b and not r.get("undo_of") and b not in order and b not in undone:
            order.append(b)
    return order


def do_undo(home: Home, batch: str | None = None) -> dict:
    if not take_lock(home):
        return {"ok": False, "error": "A sort is running. Try the undo again in a minute."}
    try:
        log = read_log(home)
        undone = {r.get("undo_of") for r in log if r.get("undo_of")}
        if batch is None:
            open_batches = batches(home)
            if not open_batches:
                return {"ok": False, "error": "Nothing to undo: no sort has moved files yet (or it was already undone)."}
            batch = open_batches[-1]
        elif batch in undone:
            return {"ok": False, "error": f"Batch {batch} was already undone."}
        moves = [r for r in log if r.get("batch") == batch and not r.get("undo_of")]
        if not moves:
            return {"ok": False, "error": f"No moves found for batch {batch}."}
        restored, problems, rows = [], [], []
        for r in reversed(moves):
            src, dst = home.abs(r["to"]), home.abs(r["from"])
            if not src.exists():
                problems.append({"file": r["to"], "why": "it is not there any more (moved or deleted since)"})
                continue
            why = safe_move(src, dst)
            if why:
                problems.append({"file": r["to"], "why": f"could not put it back at {r['from']}: {why}"})
                continue
            rows.append({"batch": f"undo-{batch}", "undo_of": batch, "ts": now_iso(), "from": r["to"],
                         "to": r["from"], "reason": "undo"})
            restored.append(r["from"])
        append_log(home, rows)
        for g in GROUPS:   # remove group folders the sort made, only when they are empty now
            d = home.raw / g
            if d.is_dir():
                left = [c for c in d.iterdir() if c.name != ".DS_Store"]
                if not left:
                    (d / ".DS_Store").unlink(missing_ok=True)
                    try:
                        d.rmdir()
                    except OSError:
                        pass
        cache = read_json(home.cache, {}) or {}
        build_library(home, cache, batch=None)
        lib = read_json(home.library, {})
        lib["last_batch"] = None
        write_json(home.library, lib)
        write_json(home.cache, cache)
        return {"ok": not problems, "batch": batch, "restored": len(restored), "problems": problems}
    finally:
        release_lock(home)


# ---------------------------------------------------------------- CLI glue (rr.py sort)
def say_sort(res: dict) -> str:
    if not res.get("ok"):
        return res.get("error", "Sort failed.")
    lines = []
    if res["dry_run"]:
        n = len(res["planned"] or [])
        if not n:
            lines.append("Nothing new to sort in raw footage.")
        else:
            lines.append(f"Would move {n} file(s) (dry run, nothing moved):")
            for m in res["planned"]:
                lines.append(f"  {m['from']}  ->  {m['group']}/   ({m['reason']})")
    elif not res["moved"]:
        lines.append("Nothing new to sort in raw footage." if not res["left"] else "Nothing was moved.")
    else:
        lines.append(f"Sorted {res['moved']} file(s) into folders in raw footage ({res['seconds']} s, batch {res['batch']}):")
        for g, n in res["counts"].items():
            if n:
                lines.append(f"  {g:<18} {n}")
    for l in res["left"]:
        lines.append(f"Left where it is: {l['from']}  ({l['why']})")
    if res.get("moved"):
        lines.append("To put everything back: python3 scripts/rr.py sort --undo")
    return "\n".join(lines)


def say_undo(res: dict) -> str:
    if "restored" not in res:
        return res.get("error", "Undo failed.")
    lines = [f"Put back {res['restored']} file(s) from batch {res['batch']}."]
    for p in res["problems"]:
        lines.append(f"Could not restore {p['file']}: {p['why']}")
    return "\n".join(lines)


def main(argv: list[str], main_folder: Path) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="rr.py sort", description="Sort raw footage into labelled folders.")
    ap.add_argument("--dry-run", action="store_true", help="show what would move, move nothing")
    ap.add_argument("--undo", nargs="?", const="__last__", default=None, metavar="BATCH",
                    help="put the last sort (or a named batch) back exactly")
    ap.add_argument("--resort", action="store_true", help="also re-check files already in group folders")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quiet", action="store_true", help="print nothing unless something went wrong")
    a = ap.parse_args(argv)
    home = Home(main_folder)
    if a.undo is not None:
        res = do_undo(home, None if a.undo == "__last__" else a.undo)
        text = say_undo(res)
    else:
        res = do_sort(home, dry_run=a.dry_run, resort=a.resort, quiet=a.quiet)
        text = say_sort(res)
    if a.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    elif not a.quiet or not res.get("ok"):
        print(text)
    return 0 if res.get("ok") else 1
