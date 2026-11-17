#!/usr/bin/env python3
"""ReelReady Studio: one local page with three tabs, Library (#library), Review (#review), Styles (#styles).

    python3 studio/serve.py                 # serve and open the browser on #library
    python3 studio/serve.py --no-open       # don't open a browser tab (also: REELREADY_NO_BROWSER=1)
    python3 studio/serve.py --page review   # open on #review
    python3 studio/serve.py --port 4900     # else reelready.config.json studio.port, default 4810
    python3 studio/serve.py --sort          # sort new clips in raw footage first (in the background)

Standard library only. Listens on 127.0.0.1 only; if the port is busy it tries the next nine.
Serves the files in studio/, the built style guide page, and, for media and thumbnails, only files inside
the main folder's raw footage, exports, assets, references and .reelready/work (never .env or other hidden
files). Writes <main>/.reelready/studio.json ({pid, port, url, started}) while it runs. Ctrl+C to stop.

API: GET /api/status, GET /api/library, GET /api/exports, GET|POST /api/review/<export>, GET /media/<path>
(HTTP Range supported so video seeking works).
"""
from __future__ import annotations

import argparse
import http.server
import json
import mimetypes
import os
import socketserver
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SG = REPO / "styleguide"
sys.path.insert(0, str(REPO / "scripts"))
sys.dont_write_bytecode = True
import rr  # noqa: E402
import review as rv  # noqa: E402
import sorter  # noqa: E402

APP_ID = "reelready-studio"
DEFAULT_PORT = 4810
MEDIA_ROOTS = {"raw footage", "exports", "assets", "references"}
MAX_BODY = 1_000_000
PAGES = ("library", "review", "styles")
TYPES = {".mov": "video/mp4", ".m4v": "video/mp4", ".mp4": "video/mp4", ".m4a": "audio/mp4", ".mp3": "audio/mpeg",
         ".wav": "audio/wav", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
         ".webp": "image/webp", ".heic": "image/heic", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".html": "text/html; charset=utf-8", ".svg": "image/svg+xml",
         ".json": "application/json; charset=utf-8"}


def config_port() -> int:
    cfg = rr.config()
    for port in ((cfg.get("studio") or {}).get("port"), (cfg.get("styleguide") or {}).get("port")):
        if isinstance(port, int) and 0 < port < 65536:
            return port
    return DEFAULT_PORT


def no_browser() -> bool:
    return os.environ.get("REELREADY_NO_BROWSER", "").strip() not in ("", "0", "false", "no")


def studio_file(home: Path | None) -> Path | None:
    return Path(home) / ".reelready" / "studio.json" if home else None


def running_url(home: Path | None) -> str | None:
    """URL of a Studio already serving this main folder (checked over HTTP), else None."""
    sf = studio_file(home)
    if not sf or not sf.exists():
        return None
    try:
        info = json.loads(sf.read_text(encoding="utf-8"))
        with urllib.request.urlopen(f"http://127.0.0.1:{int(info['port'])}/api/status", timeout=1.5) as r:
            st = json.loads(r.read().decode("utf-8"))
        if st.get("app") == APP_ID and st.get("main_folder") == str(home):
            return info["url"]
    except Exception:
        return None
    return None


def waiting_export(home: Path | None) -> str | None:
    """Newest export whose review-request.json has no newer review.json yet."""
    if not home:
        return None
    best = None
    for req in (Path(home) / "exports").glob(f"*/{rv.REQUEST}"):
        if rv.fresh_review(req.parent) is None:
            m = req.stat().st_mtime
            if best is None or m > best[0]:
                best = (m, req.parent.name)
    return best[1] if best else None


# ---------------------------------------------------------------- request handler
class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "ReelReadyStudio/1"
    home: Path | None = None   # set in main()
    port = DEFAULT_PORT

    # -- helpers
    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _json(self, code: int, data):
        self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _err(self, code: int, msg: str):
        self._json(code, {"ok": False, "error": msg})

    def _host_ok(self) -> bool:
        """Only answer requests addressed to this machine (blocks DNS-rebinding pages)."""
        host = (self.headers.get("Host") or "").lower()
        return host in {f"localhost:{self.port}", f"127.0.0.1:{self.port}", f"[::1]:{self.port}"}

    def _file(self, path: Path, ctype: str | None = None):
        try:
            body = path.read_bytes()
        except OSError:
            return self._err(404, "not found")
        self._send(200, body, ctype or TYPES.get(path.suffix.lower(), "application/octet-stream"))

    # -- routing
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._host_ok():
            return self._err(403, "forbidden")
        path = urllib.parse.urlsplit(self.path).path
        if path in ("/", "/index.html"):
            return self._file(HERE / "index.html")
        if path in ("/styleguide", "/styleguide/", "/styleguide/index.html"):
            return self._file(SG / "index.html")
        if path in ("/reelready.config.json", "/styleguide/reelready.config.json"):
            return self._file(REPO / "reelready.config.json")
        if path == "/api/status":
            return self._json(200, self.status())
        if path == "/api/library":
            return self.library()
        if path == "/api/exports":
            return self.exports()
        if path.startswith("/api/review/"):
            return self.get_review(urllib.parse.unquote(path[len("/api/review/"):]))
        if path.startswith("/media/"):
            return self.media(urllib.parse.unquote(path[len("/media/"):]))
        # app files: anything directly inside studio/ except this server
        name = urllib.parse.unquote(path.lstrip("/"))
        if name and "/" not in name and "\\" not in name and not name.startswith(".") and not name.endswith(".py"):
            f = (HERE / name).resolve()
            if f.parent == HERE and f.is_file():
                return self._file(f)
        return self._err(404, "not found")

    def do_POST(self):
        if not self._host_ok():
            return self._err(403, "forbidden")
        origin = self.headers.get("Origin")
        if origin and origin.lower() not in {f"http://localhost:{self.port}", f"http://127.0.0.1:{self.port}",
                                             f"http://[::1]:{self.port}"}:
            return self._err(403, "forbidden")
        if not (self.headers.get("Content-Type") or "").lower().startswith("application/json"):
            return self._err(415, "send JSON")
        path = urllib.parse.urlsplit(self.path).path
        if not path.startswith("/api/review/"):
            return self._err(404, "not found")
        return self.post_review(urllib.parse.unquote(path[len("/api/review/"):]))

    # -- api
    def status(self) -> dict:
        cfg = rr.config()
        home = self.home
        return {"app": APP_ID, "configured": bool(home and home.exists()), "main_folder": str(home) if home else None,
                "brand": cfg.get("brand", {}), "port": self.port, "waiting_review": waiting_export(home)}

    def library(self):
        home = self.home
        if not home or not home.exists():
            return self._json(200, {"configured": False, "items": [], "groups": sorter.GROUPS})
        h = sorter.Home(home)
        lib = sorter.read_json(h.library, None) or {"version": sorter.LIB_VERSION, "groups": sorter.GROUPS,
                                                     "counts": {g: 0 for g in sorter.GROUPS}, "items": [],
                                                     "last_batch": None}
        st = sorter.read_json(h.status, {}) or {}
        sorting = bool(st.get("running")) and sorter._pid_alive(int(st.get("pid") or 0))
        lib.update({"configured": True, "main_folder": str(home), "raw_footage": str(h.raw),
                    "sorting": {"total": st.get("total"), "done": st.get("done")} if sorting else None,
                    "pending": len(sorter.pending(h))})
        return self._json(200, lib)

    def _export_dir(self, name: str) -> Path | None:
        if not self.home or not name or name.startswith(".") or "/" in name or "\\" in name or "\x00" in name:
            return None
        base = (self.home / "exports").resolve()
        d = (base / name).resolve()
        return d if d.parent == base and d.is_dir() else None

    def exports(self):
        out = []
        if self.home:
            for req in (self.home / "exports").glob(f"*/{rv.REQUEST}"):
                d = req.parent
                try:
                    r = json.loads(req.read_text(encoding="utf-8"))
                except ValueError:
                    r = {}
                rev = rv.fresh_review(d)
                out.append({"name": d.name, "title": r.get("title") or d.name,
                            "requested": req.stat().st_mtime, "approved_at": (rev or {}).get("approved_at"),
                            "waiting": rev is None})
        out.sort(key=lambda e: -e["requested"])
        return self._json(200, {"exports": out})

    def _media_rel(self, p: str | None) -> str | None:
        """A path from a request file -> path relative to the main folder, if it is servable."""
        if not p or not self.home:
            return None
        cand = Path(p)
        full = cand if cand.is_absolute() else self.home / cand
        ok = self._safe_media(full)
        return ok.relative_to(self.home.resolve()).as_posix() if ok else None

    def get_review(self, name: str):
        d = self._export_dir(name)
        if d is None or not (d / rv.REQUEST).exists():
            return self._err(404, "no review waiting for that export")
        try:
            req = json.loads((d / rv.REQUEST).read_text(encoding="utf-8"))
        except ValueError:
            return self._err(500, "review-request.json is not valid JSON")
        rev = rv.fresh_review(d)
        stale = (d / rv.REVIEW).exists() and rev is None
        draft = self._media_rel(req.get("draft"))
        return self._json(200, {"export": d.name, "request": req, "review": rev, "stale_review": stale,
                                "draft_url": "/media/" + urllib.parse.quote(draft) if draft else None,
                                "problems": rv.check_request(req)})

    def post_review(self, name: str):
        d = self._export_dir(name)
        if d is None or not (d / rv.REQUEST).exists():
            return self._err(404, "no review waiting for that export")
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > MAX_BODY:
            return self._err(413, "empty or too large")
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8"))
            req = json.loads((d / rv.REQUEST).read_text(encoding="utf-8"))
        except ValueError:
            return self._err(400, "not valid JSON")
        errs = rv.check_review(body, req)
        raw = (self.home / "raw footage").resolve()
        for s in body.get("swaps") or [] if isinstance(body, dict) else []:
            p = self._safe_media(self.home / str((s.get("library_item") or {}).get("path") or ""))
            if p is None or raw not in p.parents:
                errs.append(f"swap for cut {s.get('cut')}: that shot isn't in raw footage")
        if errs:
            return self._json(400, {"ok": False, "errors": errs})
        doc = {"export": d.name, "request_hash": rv.request_hash(d / rv.REQUEST),
               "decisions": body["decisions"], "trims": body.get("trims") or [], "swaps": body.get("swaps") or [],
               "hook": body.get("hook"), "approved_at": rv.now_iso(), "approved_in": "studio"}
        rv.write_json(d / rv.REVIEW, doc)
        return self._json(200, {"ok": True, "review": doc})

    def _safe_media(self, full: Path) -> Path | None:
        home = self.home.resolve()
        try:
            p = Path(full).resolve()
            rel = p.relative_to(home).parts
        except (ValueError, OSError, RuntimeError):
            return None
        if not rel or not p.is_file():
            return None
        if rel[0] == ".reelready":
            if len(rel) < 3 or rel[1] != "work":
                return None
            rest = rel[2:]
        elif rel[0] in MEDIA_ROOTS:
            rest = rel[1:]
        else:
            return None
        if any(part.startswith(".") for part in rest) or p.name.lower().startswith(".env"):
            return None
        return p

    def media(self, rel: str):
        if not self.home or "\x00" in rel or not rel:
            return self._err(404, "not found")
        p = self._safe_media(self.home / rel)
        if p is None:
            return self._err(403, "not allowed")
        size = p.stat().st_size
        ctype = TYPES.get(p.suffix.lower()) or mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        start, end = 0, size - 1
        rng = (self.headers.get("Range") or "").strip()
        partial = False
        if rng.startswith("bytes=") and "," not in rng:
            a, _, b = rng[6:].partition("-")
            try:
                if a == "" and b:
                    start, end = max(0, size - int(b)), size - 1
                else:
                    start = int(a)
                    end = min(int(b), size - 1) if b else size - 1
                partial = True
            except ValueError:
                partial = False
            if partial and (start > end or start >= size):
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        length = end - start + 1 if size else 0
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store" if rel.startswith("exports/") else "private, max-age=300")
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD" or not length:
            return
        try:
            with open(p, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True    # a restart gets the same port right away (old sockets in TIME_WAIT)


# ---------------------------------------------------------------- main
def build_styleguide(quiet=True) -> None:
    sys.path.insert(0, str(SG))
    try:
        import build  # noqa: E402
        if not build.build(quiet=quiet):
            print("note: style guide build failed; serving the last good page")
    except Exception as exc:  # the committed index.html still works without a build
        print(f"note: style guide build unavailable ({exc}); serving the committed page")


def serve(page="library", port=None, open_browser=True, do_build=True, sort_first=False, label="Studio") -> int:
    home = rr.main_folder()
    home = home if home and home.exists() else None
    if do_build:
        build_styleguide()
    live = running_url(home) if port is None else None
    if live:   # one Studio per main folder: reuse it
        url = live + (f"#{page}" if page in PAGES else "")
        if sort_first and sorter.pending(sorter.Home(home)):
            threading.Thread(target=lambda: sorter.do_sort(sorter.Home(home), quiet=True)).start()
        print(f"{label} running at {url}  (already open)", flush=True)
        if open_browser and not no_browser():
            webbrowser.open(url)
        return 0
    port = port or config_port()
    httpd = None
    for p in range(port, port + 10):
        try:
            httpd = Server(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    if httpd is None:
        print(f"ports {port}-{port + 9} are all busy", file=sys.stderr)
        return 1
    Handler.home, Handler.port = home, port
    base = f"http://localhost:{port}/"
    sf = studio_file(home)
    if sf:
        rv.write_json(sf, {"pid": os.getpid(), "port": port, "url": base, "started": rv.now_iso()})
    if sort_first and home:
        threading.Thread(target=lambda: sorter.do_sort(sorter.Home(home), quiet=True), daemon=True).start()
    url = base + (f"#{page}" if page in PAGES else "")
    print(f"{label} running at {url}  (Ctrl+C to stop)", flush=True)
    if open_browser and not no_browser():
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    def _term(*_):
        raise KeyboardInterrupt
    try:
        import signal
        signal.signal(signal.SIGTERM, _term)   # `rr.py studio --stop`: clean up studio.json too
    except (ValueError, OSError, AttributeError):
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
        try:
            if sf and sf.exists() and json.loads(sf.read_text(encoding="utf-8")).get("pid") == os.getpid():
                sf.unlink()
        except (OSError, ValueError):
            pass
    return 0


def main(argv=None, default_page="library", label="Studio") -> int:
    ap = argparse.ArgumentParser(description="ReelReady Studio (Library, Review, Styles)")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--page", choices=PAGES, default=default_page)
    ap.add_argument("--no-open", action="store_true", help="don't open a browser tab")
    ap.add_argument("--no-build", action="store_true", help="serve the style guide page as-is")
    ap.add_argument("--sort", action="store_true", help="sort new clips in raw footage first")
    a = ap.parse_args(argv)
    return serve(a.page, a.port, not a.no_open, not a.no_build, a.sort, label)


if __name__ == "__main__":
    sys.exit(main())
