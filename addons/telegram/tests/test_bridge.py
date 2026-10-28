"""Offline tests for bridge.py. Run: python3 -m unittest discover -s addons/telegram/tests -v
Telegram and Claude are mocked; no network, no token needed."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import bridge  # noqa: E402

FAKE = json.loads((HERE / "fake_updates.json").read_text())["result"]
OWNER = 111111
TOKEN = "123456:TEST-TOKEN-NOT-REAL"


def ok(result):
    resp = mock.Mock()
    resp.json.return_value = {"ok": True, "result": result}
    return resp


class FakeHTTP:
    """Stands in for requests.post / requests.get and records every call."""

    def __init__(self, file_error=None):
        self.posts = []
        self.file_error = file_error

    def post(self, url, data=None, files=None, timeout=None):
        method = url.rsplit("/", 1)[-1]
        self.posts.append((method, dict(data or {}), bool(files)))
        if method == "getFile":
            if self.file_error:
                r = mock.Mock()
                r.json.return_value = {"ok": False, "error_code": 400,
                                       "description": self.file_error}
                return r
            return ok({"file_path": "videos/file_1.mp4"})
        return ok({"message_id": 9})

    def get(self, url, stream=False, timeout=None):
        r = mock.MagicMock()
        r.__enter__.return_value = r
        r.iter_content.return_value = [b"FAKE-VIDEO-BYTES" * 100]
        r.raise_for_status.return_value = None
        return r

    def methods(self):
        return [m for m, _, _ in self.posts]


def make_bridge(tmp, dry_run=True, env_extra=None):
    env = {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_ALLOWED_CHAT_IDS": str(OWNER)}
    env.update(env_extra or {})
    cfg = bridge.Config(tmp, env, dry_run=dry_run)
    return bridge.Bridge(cfg, bridge.TelegramAPI(TOKEN)), cfg


class AllowlistTests(unittest.TestCase):
    def test_unknown_chat_is_ignored_completely(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, cfg = make_bridge(tmp)
            http = FakeHTTP()
            with mock.patch("bridge.requests.post", http.post), \
                 mock.patch("bridge.requests.get", http.get):
                b.handle_update(FAKE[1])  # stranger sends a video
                b.handle_update(FAKE[2])  # stranger sends a text command
            self.assertEqual(http.posts, [], "no reply, no download for strangers")
            self.assertEqual(list(cfg.raw_dir.glob("*")), [])
            self.assertEqual(list(cfg.exports_dir.glob("*")), [])

    def test_empty_allowlist_refuses_to_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(bridge.main(["--main-folder", tmp, "--dry-run",
                                          "--updates-file", str(HERE / "fake_updates.json")]), 2)

    def test_parse_chat_ids(self):
        self.assertEqual(bridge.parse_chat_ids("1, 2 -3,abc"), {1, 2, -3})


class DownloadAndEditTests(unittest.TestCase):
    def test_owner_video_downloads_edits_and_sends_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, cfg = make_bridge(tmp)
            http = FakeHTTP()
            with mock.patch("bridge.requests.post", http.post), \
                 mock.patch("bridge.requests.get", http.get):
                b.handle_update(FAKE[0])
            clips = list(cfg.raw_dir.glob("*-telegram.mp4"))
            self.assertEqual(len(clips), 1)
            self.assertGreater(clips[0].stat().st_size, 0)
            self.assertEqual(http.methods(), ["getFile", "sendMessage", "sendVideo"])
            self.assertEqual(http.posts[1][1]["text"], "Got it, editing…")
            self.assertEqual(http.posts[2][1]["chat_id"], OWNER)
            self.assertTrue(http.posts[2][2], "video was uploaded as a file")
            self.assertIn("dry run", http.posts[2][1]["caption"])
            jobs = list(cfg.jobs_dir.glob("*.json"))
            self.assertEqual(json.loads(jobs[0].read_text())["status"], "done")

    def test_text_is_forwarded_as_instruction_for_latest_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, cfg = make_bridge(tmp)
            (cfg.raw_dir / "20260101-000000-telegram.mp4").write_bytes(b"x" * 10)
            prompts = []
            real = b.run_claude
            b.run_claude = lambda p: (prompts.append(p), real(p))[1]
            http = FakeHTTP()
            with mock.patch("bridge.requests.post", http.post):
                b.handle_update(FAKE[3])
            self.assertEqual(len(prompts), 1)
            self.assertIn("use styles H1+C2", prompts[0])
            self.assertIn("20260101-000000-telegram.mp4", prompts[0])

    def test_text_without_any_clip_asks_for_a_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, _ = make_bridge(tmp)
            http = FakeHTTP()
            with mock.patch("bridge.requests.post", http.post):
                b.handle_update(FAKE[3])
            self.assertEqual(http.methods(), ["sendMessage"])
            self.assertIn("Send me a video first", http.posts[0][1]["text"])

    def test_video_document_keeps_mov_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, cfg = make_bridge(tmp)
            http = FakeHTTP()
            with mock.patch("bridge.requests.post", http.post), \
                 mock.patch("bridge.requests.get", http.get):
                b.handle_update(FAKE[4])
            self.assertEqual(len(list(cfg.raw_dir.glob("*-telegram.mov"))), 1)

    def test_too_big_video_gets_plain_language_reply_and_no_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, cfg = make_bridge(tmp)
            http = FakeHTTP()
            with mock.patch("bridge.requests.post", http.post), \
                 mock.patch("bridge.requests.get", http.get):
                b.handle_update(FAKE[5])
            self.assertEqual(http.methods(), ["sendMessage"])
            self.assertIn("too big", http.posts[0][1]["text"])
            self.assertEqual(list(cfg.raw_dir.glob("*")), [])

    def test_telegram_file_too_big_error_is_translated(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, _ = make_bridge(tmp)
            http = FakeHTTP(file_error="Bad Request: file is too big")
            upd = {"update_id": 1, "message": {"chat": {"id": OWNER},
                   "video": {"file_id": "x"}}}  # size unknown up front
            with mock.patch("bridge.requests.post", http.post):
                b.handle_update(upd)
            self.assertIn("too big", http.posts[-1][1]["text"])

    def test_claude_failure_gives_plain_error_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, cfg = make_bridge(tmp, dry_run=False)
            b.run_claude = mock.Mock(side_effect=subprocess.TimeoutExpired("claude", 1))
            http = FakeHTTP()
            with mock.patch("bridge.requests.post", http.post), \
                 mock.patch("bridge.requests.get", http.get):
                b.handle_update(FAKE[0])
            self.assertIn("taking too long", http.posts[-1][1]["text"])
            self.assertEqual(len(list(cfg.raw_dir.glob("*-telegram.mp4"))), 1)


class HelperTests(unittest.TestCase):
    def test_token_never_appears_in_api_errors(self):
        api = bridge.TelegramAPI(TOKEN)
        boom = mock.Mock(side_effect=RuntimeError(f"failed for https://x/bot{TOKEN}/getMe"))
        with mock.patch("bridge.requests.post", boom):
            with self.assertRaises(bridge.ApiError) as cm:
                api.call("getMe")
        self.assertNotIn(TOKEN, str(cm.exception))

    def test_compress_runs_ffmpeg_with_crf_28_when_too_big(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "2026-01-01-x" / "final.mp4"
            src.parent.mkdir()
            src.write_bytes(b"x" * 1000)
            seen = []

            def fake_run(cmd, **kw):
                seen.append(cmd)
                Path(cmd[-1]).write_bytes(b"x" * 10)

            with mock.patch("bridge.shutil.which", return_value="/usr/bin/ffmpeg"), \
                 mock.patch("bridge.subprocess.run", fake_run):
                out = bridge.compress_for_telegram(src, 100, Path(tmp) / "work")
            self.assertIsNotNone(out)
            self.assertIn("28", seen[0])
            self.assertLessEqual(out.stat().st_size, 100)

    def test_small_file_is_not_recompressed(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "final.mp4"
            src.write_bytes(b"x")
            self.assertEqual(bridge.compress_for_telegram(src, 100, tmp), src)

    def test_summary_is_last_three_lines(self):
        self.assertEqual(bridge.three_line_summary("a\n\nb\nc\nd\n"), "b\nc\nd")


class DryRunCliTests(unittest.TestCase):
    def test_dry_run_with_fake_updates_file_is_fully_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_dir = Path(tmp) / ".reelready"
            env_dir.mkdir()
            (env_dir / ".env").write_text(f"TELEGRAM_ALLOWED_CHAT_IDS={OWNER}\n")
            with mock.patch("bridge.requests.post", side_effect=AssertionError("network used")), \
                 mock.patch("bridge.requests.get", side_effect=AssertionError("network used")):
                code = bridge.main(["--main-folder", tmp, "--dry-run",
                                    "--updates-file", str(HERE / "fake_updates.json")])
            self.assertEqual(code, 0)
            raw = Path(tmp) / "raw footage"
            self.assertEqual(len(list(raw.glob("*-telegram.mp4"))) + len(list(raw.glob("*-telegram.mov"))), 2)
            self.assertTrue(list((Path(tmp) / "exports").glob("*/final.mp4")))


if __name__ == "__main__":
    unittest.main()
