#!/usr/bin/env python3
"""ReelReady Telegram bridge.

Record a video on your phone, send it to your Telegram bot, and the edited
video comes back. Everything runs on your own computer.

Flow:
  1. Long-poll Telegram for new messages (only from allowlisted chat ids).
  2. Download incoming videos into "<main folder>/raw footage/".
  3. Run Claude Code headless in the main folder (REELREADY_CLAUDE_CMD).
  4. Find the newest exports/*/final.mp4 made by that run and send it back.

Config lives in <main folder>/.reelready/.env:
  TELEGRAM_BOT_TOKEN=...             (from @BotFather)
  TELEGRAM_ALLOWED_CHAT_IDS=123,456  (comma separated)
Optional:
  REELREADY_CLAUDE_CMD="claude -p"   command that receives the prompt as its last argument
  REELREADY_JOB_TIMEOUT=1800         seconds before an edit is abandoned
  REELREADY_MAX_UPLOAD_BYTES=49000000
  TELEGRAM_API_BASE=https://api.telegram.org   (point at a local Bot API server to lift size caps)

Usage:
  python3 bridge.py --main-folder "/path/to/AI Video Editor"
  python3 bridge.py --main-folder ... --find-chat-id     # print your chat id, then exit
  python3 bridge.py --main-folder ... --dry-run          # fake the claude call
  python3 bridge.py --main-folder ... --dry-run --updates-file tests/fake_updates.json
                                                          # fully offline test run

Only needs Python 3 and `requests`. ffmpeg is used only to shrink big exports.
"""
import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

DEFAULT_PROMPT = "edit the newest clip in raw footage, use my default mix, just do it"
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
# Telegram's public Bot API lets a bot download files up to 20 MB and upload up to 50 MB.
DOWNLOAD_LIMIT = 20 * 1024 * 1024
DEFAULT_MAX_UPLOAD = 49_000_000

HELP_TEXT = (
    "Send me a video and I will edit it and send it back.\n"
    "Send a text after a video to change the edit, for example: use styles H1+C2"
)
TOO_BIG_TEXT = (
    "That video is too big for me to download (Telegram lets bots take about 20 MB). "
    "Try sending it as a normal video instead of a file, trim it to under a minute, "
    "or drop it straight into the raw footage folder on your computer."
)


def log(msg):
    print(time.strftime("%Y-%m-%d %H:%M:%S"), msg, flush=True)


# ---------------------------------------------------------------- config

def load_env_file(path):
    """Parse KEY=VALUE lines. Real environment variables win over the file."""
    values = {}
    p = Path(path)
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            values[key.strip()] = val
    for key in list(values):
        if key in os.environ:
            values[key] = os.environ[key]
    for key in ("REELREADY_CLAUDE_CMD", "REELREADY_JOB_TIMEOUT",
                "REELREADY_MAX_UPLOAD_BYTES", "TELEGRAM_API_BASE"):
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def parse_chat_ids(raw):
    ids = set()
    for part in re.split(r"[,\s]+", raw or ""):
        if part.lstrip("-").isdigit():
            ids.add(int(part))
    return ids


class Config:
    def __init__(self, main_folder, env, dry_run=False):
        self.main = Path(main_folder).expanduser().resolve()
        self.dry_run = dry_run
        self.token = env.get("TELEGRAM_BOT_TOKEN", "")
        self.allowed = parse_chat_ids(env.get("TELEGRAM_ALLOWED_CHAT_IDS", ""))
        self.claude_cmd = shlex.split(env.get("REELREADY_CLAUDE_CMD") or "claude -p")
        self.timeout = int(env.get("REELREADY_JOB_TIMEOUT") or 1800)
        self.max_upload = int(env.get("REELREADY_MAX_UPLOAD_BYTES") or DEFAULT_MAX_UPLOAD)
        self.api_base = (env.get("TELEGRAM_API_BASE") or "https://api.telegram.org").rstrip("/")
        self.raw_dir = self.main / "raw footage"
        self.exports_dir = self.main / "exports"
        self.work_dir = self.main / ".reelready" / "work"
        self.jobs_dir = self.work_dir / "jobs"
        self.state_file = self.work_dir / "telegram-state.json"


# ---------------------------------------------------------------- telegram api

class ApiError(Exception):
    def __init__(self, description, code=None):
        super().__init__(description)
        self.code = code


class TelegramAPI:
    def __init__(self, token, base="https://api.telegram.org"):
        self.token = token
        self.url = f"{base}/bot{token}"
        self.file_url = f"{base}/file/bot{token}"

    def _scrub(self, text):
        return str(text).replace(self.token, "***") if self.token else str(text)

    def call(self, method, data=None, files=None, timeout=30):
        try:
            r = requests.post(f"{self.url}/{method}", data=data or {}, files=files, timeout=timeout)
            body = r.json()
        except Exception as exc:  # network or bad JSON; never leak the token in the message
            raise ApiError(self._scrub(exc)) from None
        if not body.get("ok"):
            raise ApiError(body.get("description", "unknown error"), body.get("error_code"))
        return body.get("result")

    def get_updates(self, offset, timeout=25):
        return self.call("getUpdates", {"offset": offset, "timeout": timeout,
                                        "allowed_updates": json.dumps(["message"])},
                         timeout=timeout + 10) or []

    def send_message(self, chat_id, text):
        return self.call("sendMessage", {"chat_id": chat_id, "text": text})

    def send_video(self, chat_id, path, caption=""):
        with open(path, "rb") as fh:
            return self.call("sendVideo", {"chat_id": chat_id, "caption": caption[:1000],
                                           "supports_streaming": "true"},
                             files={"video": fh}, timeout=600)

    def send_document(self, chat_id, path, caption=""):
        with open(path, "rb") as fh:
            return self.call("sendDocument", {"chat_id": chat_id, "caption": caption[:1000]},
                             files={"document": fh}, timeout=600)

    def get_file(self, file_id):
        return self.call("getFile", {"file_id": file_id})

    def download(self, file_path, dest):
        if os.path.isabs(file_path) and os.path.exists(file_path):  # local Bot API server
            shutil.copyfile(file_path, dest)
            return
        try:
            with requests.get(f"{self.file_url}/{file_path}", stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(dest, "wb") as out:
                    for chunk in r.iter_content(1024 * 256):
                        out.write(chunk)
        except Exception as exc:
            raise ApiError(self._scrub(exc)) from None


class OfflineAPI:
    """Used by --dry-run with --updates-file. Prints instead of calling Telegram."""

    def __init__(self):
        self.sent = []

    def get_updates(self, offset, timeout=25):
        return []

    def send_message(self, chat_id, text):
        self.sent.append(("message", chat_id, text))
        log(f"[offline] to {chat_id}: {text}")

    def send_video(self, chat_id, path, caption=""):
        self.sent.append(("video", chat_id, str(path)))
        log(f"[offline] to {chat_id}: video {path} ({Path(path).stat().st_size} bytes) caption={caption!r}")

    send_document = send_video

    def get_file(self, file_id):
        return {"file_path": f"offline/{file_id}.mp4"}

    def download(self, file_path, dest):
        Path(dest).write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"offline-fake-video" * 8)


# ---------------------------------------------------------------- helpers

def extract_video(msg):
    """Return (file_id, size) for a video-ish message, else None."""
    for key in ("video", "video_note"):
        if msg.get(key):
            return msg[key]["file_id"], msg[key].get("file_size") or 0, ".mp4"
    doc = msg.get("document")
    if doc:
        name_ext = Path(doc.get("file_name") or "").suffix.lower()
        if (doc.get("mime_type") or "").startswith("video/") or name_ext in VIDEO_EXTS:
            ext = name_ext if name_ext in VIDEO_EXTS else ".mp4"
            return doc["file_id"], doc.get("file_size") or 0, ext
    return None


def newest_clip(raw_dir):
    clips = [p for p in Path(raw_dir).glob("*") if p.suffix.lower() in VIDEO_EXTS]
    return max(clips, key=lambda p: p.stat().st_mtime) if clips else None


def newest_export(exports_dir, since):
    best = None
    for f in Path(exports_dir).glob("*/final.mp4"):
        m = f.stat().st_mtime
        if m >= since and (best is None or m > best[0]):
            best = (m, f)
    return best[1] if best else None


def three_line_summary(stdout):
    lines = [ln.strip() for ln in (stdout or "").splitlines() if ln.strip()]
    text = "\n".join(lines[-3:]) if lines else "Done."
    return text[:900]


def compress_for_telegram(src, max_bytes, work_dir):
    """Return a path under max_bytes (the original if it already fits), else None."""
    src = Path(src)
    if src.stat().st_size <= max_bytes:
        return src
    if not shutil.which("ffmpeg"):
        return None
    out = Path(work_dir) / f"{src.parent.name}-telegram-small.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    for crf, scale in (("28", None), ("32", "scale=-2:1280")):
        cmd = ["ffmpeg", "-y", "-i", str(src), "-c:v", "libx264", "-crf", crf,
               "-preset", "veryfast", "-c:a", "aac", "-b:a", "96k",
               "-movflags", "+faststart"]
        if scale:
            cmd += ["-vf", scale]
        cmd.append(str(out))
        subprocess.run(cmd, capture_output=True, timeout=1800)
        if out.exists() and out.stat().st_size <= max_bytes:
            return out
    return None


# ---------------------------------------------------------------- bridge

class Bridge:
    def __init__(self, cfg, api):
        self.cfg = cfg
        self.api = api
        for d in (cfg.raw_dir, cfg.exports_dir, cfg.jobs_dir):
            d.mkdir(parents=True, exist_ok=True)

    # state so a restart never replays old messages
    def load_offset(self):
        try:
            return int(json.loads(self.cfg.state_file.read_text())["offset"])
        except Exception:
            return 0

    def save_offset(self, offset):
        self.cfg.state_file.write_text(json.dumps({"offset": offset}))

    def handle_update(self, upd):
        msg = upd.get("message")
        if not msg:
            return
        chat_id = (msg.get("chat") or {}).get("id")
        if chat_id not in self.cfg.allowed:
            # Silent on purpose: strangers get no reply and no way to trigger anything.
            log(f"ignored a message from chat {chat_id} (not on the allowlist)")
            return
        media = extract_video(msg)
        if media:
            self.handle_video(chat_id, *media)
        elif msg.get("text"):
            self.handle_text(chat_id, msg["text"].strip())
        else:
            self.api.send_message(chat_id, "I can only work with videos and text messages.")

    def handle_video(self, chat_id, file_id, size, ext):
        if size and size > DOWNLOAD_LIMIT and self.cfg.api_base == "https://api.telegram.org":
            self.api.send_message(chat_id, TOO_BIG_TEXT)
            return
        try:
            info = self.api.get_file(file_id)
            stamp = time.strftime("%Y%m%d-%H%M%S")
            dest = self.cfg.raw_dir / f"{stamp}-telegram{ext}"
            n = 1
            while dest.exists():
                n += 1
                dest = self.cfg.raw_dir / f"{stamp}-{n}-telegram{ext}"
            part = dest.with_suffix(dest.suffix + ".part")
            self.api.download(info["file_path"], part)
            part.rename(dest)
        except ApiError as exc:
            if "too big" in str(exc).lower():
                self.api.send_message(chat_id, TOO_BIG_TEXT)
            else:
                log(f"download failed: {exc}")
                self.api.send_message(chat_id, "I could not download that video. Please try sending it again.")
            return
        log(f"saved {dest.name} ({dest.stat().st_size} bytes)")
        self.api.send_message(chat_id, "Got it, editing…")
        self.run_job(chat_id, dest, DEFAULT_PROMPT)

    def handle_text(self, chat_id, text):
        if text.startswith(("/start", "/help")):
            self.api.send_message(chat_id, HELP_TEXT)
            return
        clip = newest_clip(self.cfg.raw_dir)
        if not clip:
            self.api.send_message(chat_id, "Send me a video first, then tell me how you want it edited.")
            return
        self.api.send_message(chat_id, "Got it, editing…")
        prompt = (f"edit the newest clip in raw footage ({clip.name}). "
                  f"Instruction from the owner: {text}. Just do it.")
        self.run_job(chat_id, clip, prompt)

    def run_claude(self, prompt):
        """Return (returncode, stdout). Dry-run fakes the edit."""
        if self.cfg.dry_run:
            clip = newest_clip(self.cfg.raw_dir)
            out_dir = self.cfg.exports_dir / f"{time.strftime('%Y-%m-%d')}-dry-run"
            out_dir.mkdir(parents=True, exist_ok=True)
            if clip:
                shutil.copyfile(clip, out_dir / "final.mp4")
            else:
                (out_dir / "final.mp4").write_bytes(b"dry-run")
            return 0, ("Cut 3 pauses and 2 retakes.\n"
                       "Added captions and a lower-third.\n"
                       "Exported 1080x1920, about 20 seconds. (dry run)")
        proc = subprocess.run(self.cfg.claude_cmd + [prompt], cwd=self.cfg.main,
                              capture_output=True, text=True, timeout=self.cfg.timeout,
                              stdin=subprocess.DEVNULL)
        return proc.returncode, proc.stdout

    def run_job(self, chat_id, clip, prompt):
        started = time.time()
        job_file = self.cfg.jobs_dir / f"{time.strftime('%Y%m%d-%H%M%S')}.json"
        job = {"clip": str(clip), "prompt": prompt, "started": started, "status": "running"}
        job_file.write_text(json.dumps(job, indent=2))
        try:
            code, stdout = self.run_claude(prompt)
            export = newest_export(self.cfg.exports_dir, started - 1)
            if export is None:
                job["status"] = "no-output"
                self.api.send_message(chat_id, "I ran the edit but could not find a finished video. "
                                      "Try again, or open Claude on your computer to see what happened.")
                return
            small = compress_for_telegram(export, self.cfg.max_upload, self.cfg.work_dir)
            if small is None:
                job["status"] = "too-large"
                self.api.send_message(chat_id, f"The edit is done but too big to send here. "
                                      f"It is saved in exports/{export.parent.name}/final.mp4.")
                return
            summary = three_line_summary(stdout)
            try:
                self.api.send_video(chat_id, small, summary)
            except ApiError as exc:
                log(f"sendVideo failed ({exc}); trying as a file")
                self.api.send_document(chat_id, small, summary)
            job.update(status="done", export=str(export), exit_code=code)
        except subprocess.TimeoutExpired:
            job["status"] = "timeout"
            self.api.send_message(chat_id, "That edit is taking too long, so I stopped it. "
                                  "Try a shorter clip.")
        except FileNotFoundError:
            job["status"] = "no-claude"
            self.api.send_message(chat_id, "I could not start Claude on your computer. "
                                  "Check that Claude Code is installed and signed in.")
        except Exception as exc:
            job["status"] = "error"
            log(f"job failed: {exc!r}")
            self.api.send_message(chat_id, "Something went wrong while editing. "
                                  "Your original clip is safe in raw footage. Please try again.")
        finally:
            job["finished"] = time.time()
            job_file.write_text(json.dumps(job, indent=2))

    def process(self, updates):
        offset = None
        for upd in updates:
            offset = upd["update_id"] + 1
            try:
                self.handle_update(upd)
            except Exception as exc:
                log(f"update {upd.get('update_id')} failed: {exc!r}")
        return offset

    def loop(self, once=False):
        offset = self.load_offset()
        log(f"ReelReady Telegram bridge running. Main folder: {self.cfg.main}")
        while True:
            try:
                updates = self.api.get_updates(offset)
            except ApiError as exc:
                if exc.code == 401:
                    log("Telegram says the bot token is not valid. Check .reelready/.env.")
                    return 2
                log(f"getUpdates problem: {exc}")
                time.sleep(5)
                continue
            for upd in updates:
                offset = upd["update_id"] + 1
                self.save_offset(offset)  # save first, so a crash never replays a job
                try:
                    self.handle_update(upd)
                except Exception as exc:
                    log(f"update failed: {exc!r}")
            if once:
                return 0


def find_chat_id(api):
    print("Send any message to your bot now. Waiting up to 60 seconds...", flush=True)
    end = time.time() + 60
    seen = set()
    while time.time() < end:
        for upd in api.get_updates(0, timeout=10):
            chat = (upd.get("message") or {}).get("chat") or {}
            if chat.get("id") not in seen and chat.get("id") is not None:
                seen.add(chat["id"])
                name = chat.get("first_name") or chat.get("title") or ""
                print(f"chat id: {chat['id']}  ({name})", flush=True)
        if seen:
            return 0
    print("No messages seen.", flush=True)
    return 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="ReelReady Telegram bridge")
    ap.add_argument("--main-folder", required=True, help='your "AI Video Editor" folder')
    ap.add_argument("--dry-run", action="store_true", help="fake the claude call")
    ap.add_argument("--updates-file", help="JSON file of fake updates (with --dry-run: fully offline)")
    ap.add_argument("--find-chat-id", action="store_true", help="print your chat id and exit")
    ap.add_argument("--once", action="store_true", help="process one batch of updates and exit")
    args = ap.parse_args(argv)

    main_folder = Path(args.main_folder).expanduser()
    env = load_env_file(main_folder / ".reelready" / ".env")
    cfg = Config(main_folder, env, dry_run=args.dry_run)
    offline = args.dry_run and args.updates_file

    if offline:
        api = OfflineAPI()
    else:
        if not cfg.token:
            print("TELEGRAM_BOT_TOKEN is missing. Add it to .reelready/.env in your main folder.")
            return 2
        api = TelegramAPI(cfg.token, cfg.api_base)

    if args.find_chat_id:
        return find_chat_id(api)
    if not cfg.allowed:
        print("TELEGRAM_ALLOWED_CHAT_IDS is empty. Refusing to start: nobody is allowed.\n"
              "Run with --find-chat-id to learn your chat id.")
        return 2

    bridge = Bridge(cfg, api)
    if args.updates_file:
        data = json.loads(Path(args.updates_file).read_text())
        updates = data.get("result", data) if isinstance(data, dict) else data
        bridge.process(updates)
        return 0
    try:
        return bridge.loop(once=args.once)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
