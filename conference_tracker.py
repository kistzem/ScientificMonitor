#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
conference_tracker.py — Agent 10: Conference tracker.
Tracks AGU, EGU, AMS and other SAI-related conferences.
Saves: data/conferences_latest.json
"""

import argparse
import io
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import pytz
import requests

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR  = Path(__file__).parent.resolve()
OUTPUT_FILE = SCRIPT_DIR / "data" / "conferences_latest.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")
SESSION     = requests.Session()
SESSION.headers.update({"User-Agent": "ScientificMonitor/1.0 (t.kislev@stardust-initiative.com)"})

sys.path.insert(0, str(SCRIPT_DIR))
from config import TRACKED_ACADEMICS, SAI_CONFERENCES


def _s2_conference_search(query: str, limit: int = 15) -> list[dict]:
    """Search for conference papers."""
    fields = "paperId,title,authors,abstract,year,publicationDate,externalIds,publicationVenue,openAccessPdf"
    try:
        r = SESSION.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": query, "fields": fields, "limit": limit},
            timeout=15,
        )
        data = r.json().get("data", [])
    except Exception as exc:
        print(f"  S2 error: {exc}")
        return []

    results = []
    cutoff   = (datetime.now(ISRAEL_TZ) - timedelta(days=180)).strftime("%Y-%m-%d")
    tracked  = {a["name"].lower() for a in TRACKED_ACADEMICS}
    for paper in data:
        pub_date = (paper.get("publicationDate") or "")[:10]
        if pub_date < cutoff:
            continue
        venue = (paper.get("publicationVenue") or {})
        venue_name = venue.get("name") or ""
        title      = paper.get("title") or ""
        authors    = [a["name"] for a in paper.get("authors", [])]
        tracked_hit = next((a for a in authors if any(t in a.lower() for t in tracked)), None)
        ext       = paper.get("externalIds") or {}
        doi       = ext.get("DOI", "")
        arxiv_id  = ext.get("ArXiv", "")
        url_val   = (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id
                     else f"https://doi.org/{doi}" if doi
                     else f"https://www.semanticscholar.org/paper/{paper.get('paperId','')}")
        oap = paper.get("openAccessPdf") or {}
        results.append({
            "id":             f"s2:{paper.get('paperId','')}",
            "title":          title,
            "authors":        authors[:5],
            "abstract":       (paper.get("abstract") or "")[:800],
            "url":            url_val,
            "doi":            doi,
            "published_date": pub_date,
            "source":         "semantic_scholar",
            "conference":     venue_name,
            "pdf_url":        oap.get("url", ""),
            "is_open_access": bool(oap),
            "category":       "conference",
            "tracked_author": tracked_hit,
            "alert_level":    "immediate" if tracked_hit else "daily",
            "relevance_score": 8 if tracked_hit else 5,
            "saved":          False,
            "found_at":       datetime.now(ISRAEL_TZ).isoformat(),
            "keywords_matched": [],
            "contradicts_stardust": False,
            "contradiction_details": "",
        })
    return results


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[Conference Tracker] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    all_papers: list[dict] = []
    for conf in SAI_CONFERENCES:
        print(f"  {conf['abbr']}: {conf['search'][:40]}...")
        papers = _s2_conference_search(conf["search"], 12)
        for p in papers:
            if not p["conference"]:
                p["conference"] = conf["name"]
        all_papers += papers
        time.sleep(1)

    # Also search by tracked author names at conferences
    for acad in TRACKED_ACADEMICS[:8]:
        name = acad["name"]
        q    = f"{name} stratospheric aerosol conference"
        results = _s2_conference_search(q, 5)
        all_papers += results
        time.sleep(1)

    # Deduplicate
    seen = set()
    uniq = []
    for p in all_papers:
        norm = " ".join(p["title"].lower().split())[:80]
        if norm and norm not in seen and p["title"]:
            seen.add(norm)
            uniq.append(p)

    by_conference: dict[str, list] = {}
    for p in uniq:
        conf = p.get("conference") or "Unknown"
        by_conference.setdefault(conf, []).append(p)

    output = {
        "generated_at":   now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso":  now.isoformat(),
        "total":          len(uniq),
        "papers":         uniq,
        "by_conference":  {k: len(v) for k, v in by_conference.items()},
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {len(uniq)} מצגות · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
