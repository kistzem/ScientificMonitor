#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""simple_server.py — serves dashboard.html on port 5759 and runs search_agent on demand."""

import io, json, subprocess, sys, threading, webbrowser, argparse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
import pytz

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR = Path(__file__).parent.resolve()
ISRAEL_TZ  = pytz.timezone("Asia/Jerusalem")
PORT       = 5759

_lock    = threading.Lock()
_running = False
_output: list[str] = []


def _run_bg():
    global _running, _output
    _output = ["מתחיל חיפוש..."]
    try:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "search_agent.py")],
            capture_output=True, text=True, timeout=600, cwd=str(SCRIPT_DIR),
        )
        lines = (proc.stdout + proc.stderr).strip().splitlines()
        _output = [l for l in lines if l.strip()][-30:]
    except Exception as e:
        _output = [f"❌ {e}"]
    finally:
        with _lock:
            _running = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, ctype, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, "application/json; charset=utf-8",
                   json.dumps(obj, ensure_ascii=False).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/dashboard.html"):
            f = SCRIPT_DIR / "dashboard.html"
            if f.exists():
                self._send(200, "text/html; charset=utf-8", f.read_bytes())
            else:
                self._send(404, "text/plain", b"Run search_agent.py first")
        elif path == "/status":
            with _lock:
                self._json({"running": _running, "output": _output[-10:]})
        elif path == "/data":
            f = SCRIPT_DIR / "data" / "search_results.json"
            self._send(200, "application/json; charset=utf-8",
                       f.read_bytes() if f.exists() else b"{}")
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        if self.path.split("?")[0] == "/refresh":
            global _running
            with _lock:
                if _running:
                    self._json({"error": "כבר רץ"}, 409); return
                _running = True
            threading.Thread(target=_run_bg, daemon=True).start()
            self._json({"status": "started"})
        else:
            self._send(404, "text/plain", b"Not found")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    class TServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

    SCRIPT_DIR.joinpath("data").mkdir(exist_ok=True)
    srv = TServer(("localhost", PORT), Handler)
    print(f"[{datetime.now(ISRAEL_TZ).strftime('%H:%M')}] ScientificMonitor → http://localhost:{PORT}")
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
