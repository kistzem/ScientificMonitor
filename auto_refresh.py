#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_refresh.py — runs the full ScientificMonitor pipeline.
Called by Windows Task Scheduler at 09:00 and 18:00 (Mon-Fri).
Logs to: auto_refresh.log
"""

import io
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytz

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR = Path(__file__).parent.resolve()
LOG_FILE   = SCRIPT_DIR / "auto_refresh.log"
ISRAEL_TZ  = pytz.timezone("Asia/Jerusalem")

STEPS = [
    ("field_tracker.py",       ["--run"]),
    ("academic_tracker.py",    ["--run"]),
    ("network_analyzer.py",    ["--run"]),
    ("competition_tracker.py", ["--run"]),
    ("paper_analyzer.py",      ["--run"]),
    ("classifier.py",          ["--run"]),
    ("retraction_tracker.py",  ["--run"]),
    ("negative_filter.py",     ["--run"]),
    ("controversy_detector.py",["--run"]),
    ("citation_tracker.py",    ["--run"]),
    ("trend_detector.py",      ["--run"]),
    ("preprint_tracker.py",    ["--run"]),
    ("funding_tracker.py",     ["--run"]),
    ("patent_landscape.py",    ["--run"]),
    ("conference_tracker.py",  ["--run"]),
    ("policy_monitor.py",      ["--run"]),
    ("anomaly_detector.py",    ["--run"]),
    ("generate_dashboard.py",  []),
]


def _log(msg: str) -> None:
    print(msg)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main() -> None:
    now = datetime.now(ISRAEL_TZ).strftime("%d/%m/%Y %H:%M")
    _log(f"\n{'='*55}")
    _log(f"[ScientificMonitor auto_refresh] {now}")

    py = sys.executable
    ok = True
    for script, args in STEPS:
        path = SCRIPT_DIR / script
        _log(f"▶ {script}...")
        try:
            r = subprocess.run(
                [py, str(path)] + args,
                capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                timeout=600, cwd=str(SCRIPT_DIR),
            )
            tail = (r.stdout + r.stderr).strip().splitlines()[-5:]
            for line in tail:
                if line.strip():
                    _log(f"  {line}")
            if r.returncode != 0:
                _log(f"  ❌ קוד יציאה {r.returncode}")
                ok = False
            else:
                _log(f"  ✅ הסתיים")
        except subprocess.TimeoutExpired:
            _log(f"  ❌ timeout")
            ok = False
        except Exception as exc:
            _log(f"  ❌ {exc}")
            ok = False

    _log(f"[auto_refresh] {'✅ הצליח' if ok else '⚠️ חלקי'}")

    # Trim log
    try:
        lines = LOG_FILE.read_text(encoding="utf-8").splitlines()
        if len(lines) > 600:
            LOG_FILE.write_text("\n".join(lines[-500:]) + "\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()
