#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py — ScientificMonitor HTTP server on port 5759.
Serves the dashboard and exposes REST endpoints for all 12 agents.
"""

import argparse
import io
import json
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from pathlib import Path

import pytz

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_DIR   = SCRIPT_DIR / "data"
ISRAEL_TZ  = pytz.timezone("Asia/Jerusalem")
PORT       = 5759

# ── Agent pipeline (all 12) ─────────────────────────────────────────
AGENT_SCRIPTS = [
    "field_tracker.py",
    "academic_tracker.py",
    "network_analyzer.py",
    "competition_tracker.py",
    "paper_analyzer.py",
    "classifier.py",
    "retraction_tracker.py",
    "negative_filter.py",
    "controversy_detector.py",
    "citation_tracker.py",
    "trend_detector.py",
    "preprint_tracker.py",
    "funding_tracker.py",
    "patent_landscape.py",
    "conference_tracker.py",
    "policy_monitor.py",
    "anomaly_detector.py",
    "generate_dashboard.py",
]

# ── Shared state ─────────────────────────────────────────────────────
_lock    = threading.Lock()
_running = False
_output: list[str] = []


def _run_agents_bg():
    global _running, _output
    _output = []
    for script in AGENT_SCRIPTS:
        path = SCRIPT_DIR / script
        if not path.exists():
            _output.append(f"[SKIP] {script} לא נמצא")
            continue
        _output.append(f"[{script}] מריץ...")
        try:
            proc = subprocess.run(
                [sys.executable, str(path)],
                capture_output=True, text=True, timeout=300,
                cwd=str(SCRIPT_DIR),
            )
            last = (proc.stdout or proc.stderr or "").strip().split("\n")[-1]
            _output.append(f"[{script}] ✅ {last[:100]}")
        except subprocess.TimeoutExpired:
            _output.append(f"[{script}] ⚠️ Timeout (>5min)")
        except Exception as e:
            _output.append(f"[{script}] ❌ {e}")
    with _lock:
        _running = False
    print("[Server] כל הסוכנים הסתיימו.")


# ── JSON data loaders ────────────────────────────────────────────────
DATA_FILES = {
    "papers":         "papers_latest.json",
    "academics":      "academics_latest.json",
    "competition":    "competition_latest.json",
    "analysis":       "analysis_latest.json",
    "classified":     "classified_latest.json",
    "retractions":    "retractions_latest.json",
    "negatives":      "negatives_latest.json",
    "network":        "network_latest.json",
    "controversies":  "controversies_latest.json",
    "citations":      "citations_latest.json",
    "trends":         "trends_latest.json",
    "preprints":      "preprints_latest.json",
    "funding":        "funding_latest.json",
    "patents":        "patents_latest.json",
    "conferences":    "conferences_latest.json",
    "policy":         "policy_latest.json",
    "anomalies":      "anomalies_latest.json",
    "saved":          "saved_papers.json",
}


def _load(fname: str) -> dict:
    path = DATA_DIR / fname
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


# ── Request handler ──────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        pass  # suppress default access log

    def _send(self, code: int, ctype: str, body: bytes):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, "application/json; charset=utf-8", body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/" or path == "/dashboard.html":
            html_file = SCRIPT_DIR / "dashboard.html"
            if html_file.exists():
                body = html_file.read_bytes()
                self._send(200, "text/html; charset=utf-8", body)
            else:
                self._send(404, "text/plain", b"Dashboard not found. Run generate_dashboard.py first.")
            return

        if path == "/status":
            with _lock:
                self._json({"running": _running, "output": _output[-20:]})
            return

        if path == "/data":
            all_data = {k: _load(v) for k, v in DATA_FILES.items()}
            self._json(all_data)
            return

        # Individual data endpoints
        for key, fname in DATA_FILES.items():
            if path == f"/data/{key}":
                self._json(_load(fname))
                return

        self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        path = self.path.split("?")[0]
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length) if length else b""

        if path == "/refresh":
            global _running
            with _lock:
                if _running:
                    self._json({"error": "כבר רץ"}, 409)
                    return
                _running = True
            t = threading.Thread(target=_run_agents_bg, daemon=True)
            t.start()
            self._json({"status": "started"})
            return

        if path == "/save":
            try:
                req = json.loads(body)
                pid = str(req.get("id", ""))
                want_saved = bool(req.get("saved", True))
            except Exception:
                self._json({"error": "bad json"}, 400)
                return
            saved_file = DATA_DIR / "saved_papers.json"
            saved_data = _load("saved_papers.json")
            ids = set(saved_data.get("ids", []))
            if want_saved:
                ids.add(pid)
            else:
                ids.discard(pid)
            saved_data["ids"] = sorted(ids)
            DATA_DIR.mkdir(exist_ok=True)
            saved_file.write_text(json.dumps(saved_data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._json({"status": "ok", "saved_count": len(ids)})
            return

        if path == "/summary":
            summary_file = DATA_DIR / "summary_latest.json"
            if summary_file.exists():
                self._json(json.loads(summary_file.read_text(encoding="utf-8")))
            else:
                self._json({"summary_he": "לא זמין עדיין — הרץ עדכון.", "generated_at": ""})
            return

        self._send(404, "text/plain", b"Not found")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
        daemon_threads = True

    DATA_DIR.mkdir(exist_ok=True)
    server = ThreadedHTTPServer(("localhost", PORT), Handler)
    now = datetime.now(ISRAEL_TZ).strftime("%d/%m/%Y %H:%M")
    print(f"[{now}] ScientificMonitor → http://localhost:{PORT}")

    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{PORT}")).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Server] עצור.")
        server.shutdown()


if __name__ == "__main__":
    main()
