#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
classifier.py — Agent 5: Classifier.
Scores all papers and sorts them into categories.
Saves: data/classified_latest.json
Categories: academia (🔴), competition (🟡), field (🔵), patents (⚪)
"""

import argparse
import io
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytz

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR  = Path(__file__).parent.resolve()
OUTPUT_FILE = SCRIPT_DIR / "data" / "classified_latest.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")

sys.path.insert(0, str(SCRIPT_DIR))
from config import SAI_KEYWORDS, CONTRADICTION_TRIGGERS


def _load_all() -> tuple[list[dict], dict, dict]:
    """Load papers + analysis + retraction data."""
    def jload(f):
        p = SCRIPT_DIR / "data" / f
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    papers_f  = jload("papers_latest.json")
    acad_f    = jload("academics_latest.json")
    comp_f    = jload("competition_latest.json")
    anal_f    = jload("analysis_latest.json")
    saved_f   = jload("saved_papers.json")
    retr_f    = jload("retractions_latest.json")

    all_papers: list[dict] = []
    seen = set()
    for p in (papers_f.get("papers", []) + acad_f.get("papers", []) + comp_f.get("papers", [])):
        if p["id"] not in seen:
            seen.add(p["id"])
            all_papers.append(p)

    analyses   = anal_f.get("analyses", {})
    saved_ids  = set(saved_f.get("ids", []))
    retr_ids   = set(retr_f.get("retracted_ids", []))

    return all_papers, analyses, saved_ids, retr_ids


def _score(paper: dict, analysis: dict) -> int:
    """Compute relevance score 1-10."""
    score = 3  # base

    # Keyword count
    kw_count = len(paper.get("keywords_matched", []))
    score += min(kw_count, 3)

    # Tracked author/org
    if paper.get("tracked_author"):
        score += 2
    if paper.get("tracked_org"):
        score += 1

    # Very recent (last 14 days)
    pub = paper.get("published_date") or ""
    if pub:
        cutoff_new  = (datetime.now(ISRAEL_TZ) - timedelta(days=14)).strftime("%Y-%m-%d")
        cutoff_rec  = (datetime.now(ISRAEL_TZ) - timedelta(days=45)).strftime("%Y-%m-%d")
        if pub >= cutoff_new:
            score += 2
        elif pub >= cutoff_rec:
            score += 1

    # Contradiction flag
    if analysis.get("contradicts_stardust") or paper.get("contradicts_stardust"):
        score += 2

    # Open access
    if paper.get("is_open_access"):
        score += 1

    return min(score, 10)


def _determine_alert(paper: dict, score: int) -> str:
    if paper.get("tracked_author") or paper.get("tracked_org"):
        return "immediate"
    if score >= 7 or paper.get("contradicts_stardust"):
        return "daily"
    return "none"


def _determine_category(paper: dict) -> str:
    if paper.get("category") in ("academia", "competition", "patent"):
        return paper["category"]
    text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
    # Contradiction check
    if paper.get("contradicts_stardust"):
        return "contradiction"
    # Collaboration potential: workshops, collab, joint, review
    if any(w in text for w in ["collaboration", "joint effort", "workshop", "review paper",
                                "community effort", "multi-model", "working group"]):
        return "collaboration"
    if paper.get("source") == "patent":
        return "patent"
    if paper.get("tracked_author"):
        return "academia"
    if paper.get("tracked_org"):
        return "competition"
    return "field"


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[סינון וסיווג] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    all_papers, analyses, saved_ids, retr_ids = _load_all()
    print(f"  מסווג {len(all_papers)} מאמרים...")

    categories: dict = {
        "academia":      [],
        "competition":   [],
        "contradiction": [],
        "collaboration": [],
        "field":         [],
        "patent":        [],
    }

    alerts_immediate = []
    alerts_daily     = []

    for paper in all_papers:
        anal   = analyses.get(paper["id"], {})
        score  = _score(paper, anal)
        alert  = _determine_alert(paper, score)
        cat    = _determine_category(paper)

        paper["relevance_score"]     = score
        paper["alert_level"]         = alert
        paper["category"]            = cat
        paper["saved"]               = paper["id"] in saved_ids
        paper["is_retracted"]        = paper["id"] in retr_ids
        paper["summary_he"]          = anal.get("summary_he", "")
        paper["citation_suggestion"] = anal.get("citation_suggestion", "")
        paper["similar_work"]        = anal.get("similar_work", "")

        categories.get(cat, categories["field"]).append(paper)

        if alert == "immediate":
            alerts_immediate.append({
                "paper_id": paper["id"],
                "title":    paper["title"],
                "author":   paper.get("tracked_author") or paper.get("tracked_org", ""),
                "score":    score,
            })
        elif alert == "daily":
            alerts_daily.append({
                "paper_id": paper["id"],
                "title":    paper["title"],
                "score":    score,
            })

    # Sort each category by score desc, then date desc
    for cat in categories:
        categories[cat].sort(key=lambda p: (-p.get("relevance_score", 0),
                                             p.get("published_date") or ""), reverse=False)

    stats = {c: len(v) for c, v in categories.items()}
    stats["total"] = len(all_papers)

    output = {
        "generated_at":       now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso":      now.isoformat(),
        "stats":              stats,
        "categories":         categories,
        "alerts_immediate":   alerts_immediate,
        "alerts_daily":       alerts_daily,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {stats} · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
