#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
trend_detector.py — Agent 6: Trend detection.
Identifies hot topics, opinion pivots, and publication patterns in SAI field.
Saves: data/trends_latest.json
"""

import argparse
import io
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pytz

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR  = Path(__file__).parent.resolve()
OUTPUT_FILE = SCRIPT_DIR / "data" / "trends_latest.json"
HIST_FILE   = SCRIPT_DIR / "data" / "trends_history.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")

# Key SAI subtopics for trend tracking
SUBTOPICS = {
    "silica_sio2":    ["silica", "SiO2", "silicon dioxide aerosol"],
    "caco3_calcite":  ["calcium carbonate", "CaCO3", "calcite stratosphere"],
    "ozone_chem":     ["ozone depletion", "ozone chemistry", "polar stratospheric"],
    "heterogeneous":  ["heterogeneous uptake", "surface chemistry", "heterogeneous chemistry"],
    "climate_model":  ["climate model SAI", "GCM geoengineering", "model simulation SAI"],
    "injection_strat":["injection strategy", "injection altitude", "injection location"],
    "governance":     ["governance geoengineering", "regulation SAI", "policy SRM"],
    "monitoring":     ["monitoring SAI", "observation stratospheric", "lidar aerosol"],
    "new_materials":  ["novel aerosol", "new particle SAI", "non-sulfate aerosol"],
    "termination":    ["termination shock", "sudden stop aerosol", "cessation geoengineering"],
}

PIVOT_SIGNALS = ["however", "but we now", "revised", "reconsidering", "we previously",
                 "updating our view", "new evidence suggests", "we now believe"]


def _load_all_papers() -> list[dict]:
    papers = []
    for fname in ["papers_latest.json", "academics_latest.json",
                  "competition_latest.json", "preprints_latest.json"]:
        fpath = SCRIPT_DIR / "data" / fname
        if not fpath.exists():
            continue
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            papers.extend(data.get("papers", []))
        except Exception:
            pass
    seen = set()
    return [p for p in papers if not (seen.add(p["id"]) if p["id"] not in seen else True)]


def _count_by_subtopic(papers: list[dict]) -> dict[str, int]:
    counts = {k: 0 for k in SUBTOPICS}
    for p in papers:
        text = ((p.get("title") or "") + " " + (p.get("abstract") or "")).lower()
        for topic, kws in SUBTOPICS.items():
            if any(kw.lower() in text for kw in kws):
                counts[topic] += 1
    return counts


def _count_by_month(papers: list[dict]) -> dict[str, int]:
    """Count papers per month (YYYY-MM)."""
    counts: dict[str, int] = defaultdict(int)
    for p in papers:
        date = p.get("published_date") or ""
        if len(date) >= 7:
            counts[date[:7]] += 1
    return dict(sorted(counts.items()))


def _detect_hot_topics(current: dict[str, int], previous: dict[str, int]) -> list[dict]:
    """Topics with >50% increase vs previous period."""
    hot = []
    for topic, count in current.items():
        prev = previous.get(topic, 0)
        if prev == 0 and count >= 2:
            hot.append({"topic": topic, "count": count, "change_pct": 999, "label_he": SUBTOPIC_LABELS.get(topic, topic)})
        elif prev > 0 and count / prev >= 1.5:
            hot.append({"topic": topic, "count": count, "change_pct": round((count/prev-1)*100), "label_he": SUBTOPIC_LABELS.get(topic, topic)})
    hot.sort(key=lambda x: -x["change_pct"])
    return hot[:5]


def _detect_pivots(papers: list[dict]) -> list[dict]:
    """Find papers suggesting opinion changes."""
    pivots = []
    for p in papers:
        abstract = (p.get("abstract") or "").lower()
        title    = (p.get("title") or "").lower()
        sigs = [s for s in PIVOT_SIGNALS if s in abstract or s in title]
        if sigs:
            pivots.append({
                "paper_id":   p["id"],
                "title":      p.get("title", "")[:80],
                "authors":    (p.get("authors") or [])[:2],
                "date":       p.get("published_date", ""),
                "url":        p.get("url", ""),
                "signals":    sigs[:2],
                "summary_he": f"🔄 שינוי עמדה: '{p.get('title','')[:60]}' — {', '.join(sigs[:2])}",
            })
    return pivots[:10]


SUBTOPIC_LABELS = {
    "silica_sio2":    "סיליקה / SiO2",
    "caco3_calcite":  "CaCO3 / קלציט",
    "ozone_chem":     "כימיית אוזון",
    "heterogeneous":  "קליטה הטרוגנית",
    "climate_model":  "מודלי אקלים",
    "injection_strat":"אסטרטגיית הזרקה",
    "governance":     "ממשל ורגולציה",
    "monitoring":     "ניטור ומעקב",
    "new_materials":  "חומרים חדשים",
    "termination":    "הפסקה (Termination)",
}


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[Trend Detector] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    papers   = _load_all_papers()
    current  = _count_by_subtopic(papers)
    monthly  = _count_by_month(papers)

    # Load history for comparison
    previous = {}
    if HIST_FILE.exists():
        try:
            hist = json.loads(HIST_FILE.read_text(encoding="utf-8"))
            previous = hist.get("counts", {})
        except Exception:
            pass

    hot_topics = _detect_hot_topics(current, previous)
    pivots     = _detect_pivots(papers)

    # Most active authors this period
    author_counts: dict[str, int] = defaultdict(int)
    for p in papers:
        for a in (p.get("authors") or []):
            author_counts[a] += 1
    most_active = sorted(author_counts.items(), key=lambda x: -x[1])[:10]

    output = {
        "generated_at":    now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso":   now.isoformat(),
        "total_papers":    len(papers),
        "subtopic_counts": current,
        "subtopic_labels": SUBTOPIC_LABELS,
        "monthly_counts":  monthly,
        "hot_topics":      hot_topics,
        "pivots":          pivots,
        "most_active_authors": [{"name": a, "count": c} for a, c in most_active],
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    HIST_FILE.write_text(json.dumps({"counts": current, "date": now.isoformat()}, ensure_ascii=False), encoding="utf-8")

    print(f"  → {len(hot_topics)} נושאים חמים, {len(pivots)} שינויי עמדה · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
