#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preprint_tracker.py — Agent 7: Preprint intelligence.
Tracks arXiv and bioRxiv preprints for early access to research.
Saves: data/preprints_latest.json
"""

import argparse
import io
import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

import pytz
import requests

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR  = Path(__file__).parent.resolve()
OUTPUT_FILE = SCRIPT_DIR / "data" / "preprints_latest.json"
PREV_FILE   = SCRIPT_DIR / "data" / "preprints_prev.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")
SESSION     = requests.Session()
SESSION.headers.update({"User-Agent": "ScientificMonitor/1.0 (t.kislev@stardust-initiative.com)"})

sys.path.insert(0, str(SCRIPT_DIR))
from config import SAI_KEYWORDS, TRACKED_ACADEMICS, EXCLUDE_KEYWORDS


def _is_relevant(title: str, abstract: str) -> bool:
    text = (title + " " + abstract).lower()
    if any(e.lower() in text for e in EXCLUDE_KEYWORDS):
        return False
    return any(kw.lower() in text for kw in SAI_KEYWORDS)


def _search_arxiv(query: str, max_results: int = 30) -> list[dict]:
    params = {
        "search_query": f"all:{quote_plus(query)}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        r = SESSION.get("https://export.arxiv.org/api/query", params=params, timeout=20)
        r.raise_for_status()
    except Exception as exc:
        print(f"  arXiv error: {exc}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(r.text)
    except Exception:
        return []

    results = []
    cutoff = (datetime.now(ISRAEL_TZ) - timedelta(days=30)).strftime("%Y-%m-%d")
    for entry in root.findall("atom:entry", ns):
        pub_raw  = entry.findtext("atom:published", "", ns) or ""
        pub_date = pub_raw[:10]
        if pub_date < cutoff:
            continue
        title    = (entry.findtext("atom:title", "", ns) or "").replace("\n", " ").strip()
        abstract = (entry.findtext("atom:summary", "", ns) or "").replace("\n", " ").strip()
        if not _is_relevant(title, abstract):
            continue
        arxiv_id = (entry.findtext("atom:id", "", ns) or "").split("/abs/")[-1].strip()
        authors  = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
        # Check if any tracked author
        tracked_names = {a["name"].lower() for a in TRACKED_ACADEMICS}
        tracked_hit = next((a for a in authors if any(t in a.lower() for t in tracked_names)), None)

        results.append({
            "id":             f"arxiv:{arxiv_id}",
            "title":          title,
            "authors":        authors,
            "abstract":       abstract[:1200],
            "url":            f"https://arxiv.org/abs/{arxiv_id}",
            "doi":            "",
            "published_date": pub_date,
            "source":         "arxiv",
            "pdf_url":        f"https://arxiv.org/pdf/{arxiv_id}",
            "is_open_access": True,
            "is_preprint":    True,
            "server":         "arXiv",
            "category":       "preprint",
            "alert_level":    "immediate" if tracked_hit else "daily",
            "tracked_author": tracked_hit,
            "tracked_org":    None,
            "relevance_score": 9 if tracked_hit else 6,
            "saved":          False,
            "found_at":       datetime.now(ISRAEL_TZ).isoformat(),
            "keywords_matched": [kw for kw in SAI_KEYWORDS if kw.lower() in (title+" "+abstract).lower()],
            "contradicts_stardust": False,
            "contradiction_details": "",
        })
    return results


def _search_biorxiv(query: str, max_results: int = 15) -> list[dict]:
    """Search bioRxiv via their API."""
    try:
        # bioRxiv API: search in last 30 days
        server    = "biorxiv"
        interval  = f"{(datetime.now()-timedelta(days=30)).strftime('%Y-%m-%d')}/{datetime.now().strftime('%Y-%m-%d')}"
        r = SESSION.get(
            f"https://api.biorxiv.org/details/{server}/{interval}/0/json",
            timeout=20,
        )
        data = r.json().get("collection", [])
    except Exception as exc:
        print(f"  bioRxiv error: {exc}")
        return []

    results = []
    for item in data[:max_results]:
        title    = item.get("title") or ""
        abstract = item.get("abstract") or ""
        if not _is_relevant(title, abstract):
            continue
        doi      = item.get("doi", "")
        pub_date = item.get("date", "")[:10]
        authors  = [a.strip() for a in (item.get("authors") or "").split(";") if a.strip()]
        results.append({
            "id":             f"biorxiv:{doi}",
            "title":          title,
            "authors":        authors,
            "abstract":       abstract[:1200],
            "url":            f"https://www.biorxiv.org/content/{doi}",
            "doi":            doi,
            "published_date": pub_date,
            "source":         "biorxiv",
            "pdf_url":        f"https://www.biorxiv.org/content/{doi}.full.pdf",
            "is_open_access": True,
            "is_preprint":    True,
            "server":         "bioRxiv",
            "category":       "preprint",
            "alert_level":    "daily",
            "tracked_author": None,
            "tracked_org":    None,
            "relevance_score": 6,
            "saved":          False,
            "found_at":       datetime.now(ISRAEL_TZ).isoformat(),
            "keywords_matched": [],
            "contradicts_stardust": False,
            "contradiction_details": "",
        })
    return results


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[Preprint Intelligence] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    prev_ids = set()
    if PREV_FILE.exists():
        try:
            prev_ids = set(json.loads(PREV_FILE.read_text(encoding="utf-8")).get("ids", []))
        except Exception:
            pass

    all_preprints: list[dict] = []

    # arXiv primary queries
    for q in ["stratospheric aerosol injection", "heterogeneous uptake aerosol stratosphere",
               "SAI geoengineering ozone", "CaCO3 SiO2 stratosphere"]:
        print(f"  arXiv: {q[:45]}...")
        all_preprints += _search_arxiv(q, 25)
        time.sleep(2)

    # Author-specific arXiv searches
    tracked_names = [a["name"] for a in TRACKED_ACADEMICS]
    for name in tracked_names[:8]:
        parts = name.split()
        if len(parts) >= 2:
            q = f"au:{parts[-1]}_{parts[0][0]} stratospheric aerosol"
        else:
            q = f"au:{name}"
        results = _search_arxiv(q, 5)
        if results:
            print(f"  arXiv author: {name} → {len(results)} preprints")
        all_preprints += results
        time.sleep(1.5)

    # bioRxiv
    print("  bioRxiv...")
    all_preprints += _search_biorxiv("stratospheric aerosol injection", 20)

    # Deduplicate
    seen = set()
    uniq = []
    for p in all_preprints:
        norm = " ".join(p["title"].lower().split())[:80]
        if norm and norm not in seen:
            seen.add(norm)
            p["is_new"] = p["id"] not in prev_ids
            uniq.append(p)

    new_count = sum(1 for p in uniq if p.get("is_new"))

    output = {
        "generated_at":  now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso": now.isoformat(),
        "total":         len(uniq),
        "new_count":     new_count,
        "papers":        uniq,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    PREV_FILE.write_text(json.dumps({"ids": [p["id"] for p in uniq]}), encoding="utf-8")

    print(f"  → {len(uniq)} preprints ({new_count} חדשים) · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
