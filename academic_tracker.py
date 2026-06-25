#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
academic_tracker.py — Agent 2: Academic tracker.
Tracks new papers from specific researchers via Semantic Scholar + arXiv.
Saves: data/academics_latest.json
Priority: 🔴 all tracked academics — immediate alert.
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
OUTPUT_FILE = SCRIPT_DIR / "data" / "academics_latest.json"
PREV_FILE   = SCRIPT_DIR / "data" / "academics_prev.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")
SESSION     = requests.Session()
SESSION.headers.update({"User-Agent": "ScientificMonitor/1.0 (t.kislev@stardust-initiative.com)"})

sys.path.insert(0, str(SCRIPT_DIR))
from config import TRACKED_ACADEMICS, PUBMED_EMAIL


def _s2_author_papers(author_name: str, limit: int = 10) -> list[dict]:
    """Find author's recent papers via Semantic Scholar."""
    # Step 1: author search
    try:
        r = SESSION.get(
            "https://api.semanticscholar.org/graph/v1/author/search",
            params={"query": author_name, "fields": "authorId,name,affiliations", "limit": 3},
            timeout=15,
        )
        authors = r.json().get("data", [])
    except Exception as exc:
        print(f"    S2 author search error ({author_name}): {exc}")
        return []

    if not authors:
        return []
    author_id = authors[0]["authorId"]

    # Step 2: get their papers
    time.sleep(0.5)
    try:
        fields = "paperId,title,authors,abstract,year,publicationDate,externalIds,openAccessPdf"
        r2 = SESSION.get(
            f"https://api.semanticscholar.org/graph/v1/author/{author_id}/papers",
            params={"fields": fields, "limit": limit, "sort": "publicationDate:desc"},
            timeout=15,
        )
        papers_data = r2.json().get("data", [])
    except Exception as exc:
        print(f"    S2 papers error ({author_name}): {exc}")
        return []

    results = []
    cutoff = (datetime.now(ISRAEL_TZ) - timedelta(days=90)).strftime("%Y-%m-%d")
    for paper in papers_data:
        pub_date = (paper.get("publicationDate") or f"{paper.get('year', '')}-01-01")[:10]
        if pub_date and pub_date < cutoff:
            continue
        title   = paper.get("title") or ""
        abstract = paper.get("abstract") or ""
        ext     = paper.get("externalIds") or {}
        doi     = ext.get("DOI", "")
        arxiv_id = ext.get("ArXiv", "")
        url_val = (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id
                   else f"https://doi.org/{doi}" if doi
                   else f"https://www.semanticscholar.org/paper/{paper.get('paperId','')}")
        oap     = paper.get("openAccessPdf") or {}
        results.append({
            "id":              f"s2:{paper.get('paperId','')}",
            "title":           title,
            "authors":         [a["name"] for a in paper.get("authors", [])],
            "abstract":        abstract[:1200],
            "url":             url_val,
            "doi":             doi,
            "published_date":  str(pub_date),
            "source":          "semantic_scholar",
            "pdf_url":         oap.get("url", ""),
            "is_open_access":  bool(oap),
            "category":        "academia",
            "alert_level":     "immediate",
            "tracked_author":  author_name,
            "tracked_org":     None,
            "relevance_score": 9,
            "saved":           False,
            "found_at":        datetime.now(ISRAEL_TZ).isoformat(),
            "keywords_matched": [],
            "contradicts_stardust": False,
            "contradiction_details": "",
        })
    return results


def _arxiv_author_papers(author_name: str, max_results: int = 8) -> list[dict]:
    """Search arXiv for recent papers by author."""
    # arXiv author search format: au:LastName_F
    parts = author_name.split()
    if len(parts) >= 2:
        query = f"au:{parts[-1]}_{parts[0][0]}"
    else:
        query = f"au:{author_name}"

    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": query,
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        r = SESSION.get(url, params=params, timeout=15)
        r.raise_for_status()
    except Exception as exc:
        print(f"    arXiv error ({author_name}): {exc}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(r.text)
    except Exception:
        return []

    results = []
    cutoff = (datetime.now(ISRAEL_TZ) - timedelta(days=90)).strftime("%Y-%m-%d")
    for entry in root.findall("atom:entry", ns):
        pub_raw  = entry.findtext("atom:published", "", ns) or ""
        pub_date = pub_raw[:10]
        if pub_date < cutoff:
            continue
        title    = (entry.findtext("atom:title", "", ns) or "").replace("\n", " ").strip()
        abstract = (entry.findtext("atom:summary", "", ns) or "").replace("\n", " ").strip()
        arxiv_id = (entry.findtext("atom:id", "", ns) or "").split("/abs/")[-1].strip()
        authors  = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
        # Verify author name appears in author list
        name_parts = author_name.lower().split()
        if not any(all(p in a.lower() for p in name_parts[-1:]) for a in authors):
            continue
        results.append({
            "id":              f"arxiv:{arxiv_id}",
            "title":           title,
            "authors":         authors,
            "abstract":        abstract[:1200],
            "url":             f"https://arxiv.org/abs/{arxiv_id}",
            "doi":             "",
            "published_date":  pub_date,
            "source":          "arxiv",
            "pdf_url":         f"https://arxiv.org/pdf/{arxiv_id}",
            "is_open_access":  True,
            "category":        "academia",
            "alert_level":     "immediate",
            "tracked_author":  author_name,
            "tracked_org":     None,
            "relevance_score": 9,
            "saved":           False,
            "found_at":        datetime.now(ISRAEL_TZ).isoformat(),
            "keywords_matched": [],
            "contradicts_stardust": False,
            "contradiction_details": "",
        })
    return results


def _load_prev_ids() -> set:
    """Load previously seen paper IDs to detect new ones."""
    if PREV_FILE.exists():
        try:
            data = json.loads(PREV_FILE.read_text(encoding="utf-8"))
            return set(p["id"] for p in data.get("papers", []))
        except Exception:
            pass
    return set()


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[עוקב אקדמאים] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    prev_ids  = _load_prev_ids()
    all_papers: list[dict] = []
    by_author: dict = {}

    for acad in TRACKED_ACADEMICS:
        name = acad["name"]
        print(f"  {name}...")

        s2_papers = _s2_author_papers(name, 8)
        time.sleep(1)
        ax_papers = _arxiv_author_papers(name, 6)
        time.sleep(1)

        papers = s2_papers + ax_papers

        # Deduplicate within author
        seen = set()
        uniq = []
        for p in papers:
            norm = " ".join(p["title"].lower().split())[:80]
            if norm not in seen:
                seen.add(norm)
                uniq.append(p)

        # Mark new papers
        for p in uniq:
            p["is_new"] = p["id"] not in prev_ids

        by_author[name] = {
            "org":    acad.get("org", ""),
            "role":   acad.get("role", ""),
            "count":  len(uniq),
            "new":    sum(1 for p in uniq if p.get("is_new")),
            "papers": uniq,
        }
        all_papers.extend(uniq)

    output = {
        "generated_at":  now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso": now.isoformat(),
        "total":         len(all_papers),
        "new_count":     sum(1 for p in all_papers if p.get("is_new")),
        "by_author":     by_author,
        "papers":        all_papers,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    # Save current as prev for next run
    PREV_FILE.write_text(json.dumps({"papers": all_papers}, ensure_ascii=False), encoding="utf-8")

    new_count = output["new_count"]
    print(f"  → {len(all_papers)} מאמרים ({new_count} חדשים) · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
