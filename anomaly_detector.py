#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
anomaly_detector.py — Agent 12: Anomaly detection.
Detects unusual publication patterns, author gaps, and IP threats.
Saves: data/anomalies_latest.json
"""

import argparse
import io
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pytz

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR  = Path(__file__).parent.resolve()
OUTPUT_FILE = SCRIPT_DIR / "data" / "anomalies_latest.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")

sys.path.insert(0, str(SCRIPT_DIR))
from config import TRACKED_ACADEMICS


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


def _load_prev_papers() -> list[dict]:
    prev = []
    for fname in ["academics_prev.json", "preprints_prev.json"]:
        fpath = SCRIPT_DIR / "data" / fname
        if fpath.exists():
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                prev.extend(data.get("papers", []))
            except Exception:
                pass
    return prev


def _detect_publication_gaps(all_papers: list[dict]) -> list[dict]:
    """Find tracked authors who haven't published recently."""
    tracked_names = {a["name"] for a in TRACKED_ACADEMICS}
    author_last_pub: dict[str, str] = {}
    for p in all_papers:
        authors  = p.get("authors") or []
        pub_date = p.get("published_date") or ""
        if not pub_date:
            continue
        for auth in authors:
            is_tracked = any(t.lower() in auth.lower() or auth.lower() in t.lower()
                             for t in tracked_names)
            if is_tracked:
                if auth not in author_last_pub or pub_date > author_last_pub[auth]:
                    author_last_pub[auth] = pub_date

    gaps = []
    cutoff_90 = (datetime.now(ISRAEL_TZ) - timedelta(days=90)).strftime("%Y-%m-%d")
    for author, last_pub in author_last_pub.items():
        if last_pub < cutoff_90:
            days_silent = (datetime.now(ISRAEL_TZ).date() -
                           datetime.strptime(last_pub, "%Y-%m-%d").date()).days
            gaps.append({
                "type":       "publication_gap",
                "author":     author,
                "last_pub":   last_pub,
                "days_silent": days_silent,
                "severity":   "medium" if days_silent < 180 else "high",
                "msg_he":     f"📉 {author} לא פרסם {days_silent} ימים (אחרון: {last_pub})",
            })
    gaps.sort(key=lambda x: -x["days_silent"])
    return gaps[:10]


def _detect_unusual_coauthors(all_papers: list[dict]) -> list[dict]:
    """Detect when tracked authors publish with new/unexpected collaborators."""
    tracked_names = {a["name"].lower() for a in TRACKED_ACADEMICS}
    prev_papers = _load_prev_papers()
    prev_coauthor_map: dict[str, set] = defaultdict(set)
    for p in prev_papers:
        authors = p.get("authors") or []
        for i, auth in enumerate(authors):
            if any(t in auth.lower() for t in tracked_names):
                for other in authors:
                    if other != auth:
                        prev_coauthor_map[auth].add(other.lower())

    anomalies = []
    for p in all_papers:
        authors = p.get("authors") or []
        for i, auth in enumerate(authors):
            if any(t in auth.lower() for t in tracked_names):
                new_collabs = []
                for other in authors:
                    if other != auth and other.lower() not in prev_coauthor_map.get(auth, set()):
                        if len(other.split()) >= 2:
                            new_collabs.append(other)
                if new_collabs:
                    anomalies.append({
                        "type":         "new_collaboration",
                        "tracked_author": auth,
                        "new_collabs":  new_collabs[:3],
                        "paper_title":  p.get("title", "")[:80],
                        "paper_url":    p.get("url", ""),
                        "published":    p.get("published_date", ""),
                        "severity":     "low",
                        "msg_he":       f"🤝 שיתוף פעולה חדש: {auth} עם {', '.join(new_collabs[:2])}",
                    })
    return anomalies[:15]


def _detect_ip_threats(all_papers: list[dict]) -> list[dict]:
    """Look for papers/patents potentially overlapping with Stardust IP."""
    stardust_terms = ["silica aerosol stratosphere", "SiO2 geoengineering", "heterogeneous uptake silica",
                      "non-sulfate stratospheric aerosol particle"]
    threats = []
    for p in all_papers:
        text = ((p.get("title") or "") + " " + (p.get("abstract") or "")).lower()
        if any(term.lower() in text for term in stardust_terms):
            if p.get("source") == "patent":
                threats.append({
                    "type":     "ip_overlap",
                    "paper_id": p["id"],
                    "title":    p.get("title", "")[:80],
                    "authors":  (p.get("authors") or [])[:3],
                    "url":      p.get("url", ""),
                    "severity": "high",
                    "msg_he":   f"⚠️ פטנט עם חפיפה פוטנציאלית לIP של Stardust: {p.get('title','')[:60]}",
                })
    return threats


def _detect_burst_activity(all_papers: list[dict]) -> list[dict]:
    """Detect unusual spikes in author activity."""
    tracked_names = {a["name"].lower() for a in TRACKED_ACADEMICS}
    author_counts: dict[str, int] = defaultdict(int)
    for p in all_papers:
        for auth in (p.get("authors") or []):
            if any(t in auth.lower() for t in tracked_names):
                author_counts[auth] += 1

    bursts = []
    for auth, count in author_counts.items():
        if count >= 5:
            bursts.append({
                "type":     "burst_activity",
                "author":   auth,
                "count":    count,
                "severity": "low",
                "msg_he":   f"📈 פעילות יוצאת דופן: {auth} — {count} מאמרים בתקופה האחרונה",
            })
    return bursts


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[Anomaly Detector] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    all_papers = _load_all_papers()
    print(f"  סורק {len(all_papers)} מאמרים לאנומליות...")

    gaps      = _detect_publication_gaps(all_papers)
    new_collabs = _detect_unusual_coauthors(all_papers)
    ip_threats = _detect_ip_threats(all_papers)
    bursts    = _detect_burst_activity(all_papers)

    all_anomalies = ip_threats + gaps + new_collabs + bursts
    critical = [a for a in all_anomalies if a.get("severity") == "high"]
    medium   = [a for a in all_anomalies if a.get("severity") == "medium"]

    output = {
        "generated_at":   now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso":  now.isoformat(),
        "total":          len(all_anomalies),
        "critical_count": len(critical),
        "medium_count":   len(medium),
        "anomalies":      all_anomalies,
        "ip_threats":     ip_threats,
        "publication_gaps": gaps,
        "new_collabs":    new_collabs,
        "burst_activity": bursts,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {len(all_anomalies)} אנומליות ({len(critical)} קריטי) · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
