#!/usr/bin/env python3
"""Serve the ReelReady style guide locally and open it in the browser.

    python3 styleguide/serve.py            # rebuild from styles/, serve, open browser
    python3 styleguide/serve.py --no-open  # don't open a browser tab
    python3 styleguide/serve.py --port 4900

Port comes from reelready.config.json (styleguide.port), default 4810. If that
port is busy it tries the next few. Standard library only. Ctrl+C to stop.
"""
import argparse
import http.server
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

try:
    import build  # noqa: E402
except Exception as exc:  # the committed index.html still works without a build
    build = None
    print(f"note: build.py unavailable ({exc}); serving the committed index.html")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/reelready.config.json":
            cfg = ROOT / "reelready.config.json"
            if not cfg.exists():
                self.send_error(404)
                return
            body = cfg.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path not in ("/", "/index.html"):
            self.send_error(404)  # only the page itself is public
            return
        self.path = "/index.html"
        return super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    ap = argparse.ArgumentParser(description="Serve the ReelReady style guide")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--no-open", action="store_true", help="don't open a browser tab")
    ap.add_argument("--no-build", action="store_true", help="serve index.html as-is")
    args = ap.parse_args()

    port = args.port
    if build is not None:
        if port is None:
            port = build.load_config()["styleguide"]["port"]
        if not args.no_build and not build.build(quiet=True):
            print("build failed; serving the last good index.html")
    port = port or 4810

    if not (HERE / "index.html").exists():
        sys.exit("styleguide/index.html is missing. Run: python3 styleguide/build.py")

    httpd = None
    for p in range(port, port + 10):
        try:
            httpd = Server(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    if httpd is None:
        sys.exit(f"ports {port}-{port + 9} are all busy")

    url = f"http://localhost:{port}/"
    print(f"Style guide running at {url}  (Ctrl+C to stop)", flush=True)
    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
