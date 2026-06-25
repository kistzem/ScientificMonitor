#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
competition_tracker.py — Agent 3: Competition tracker.
Tracks papers and news from SAI organizations.
Saves: data/competition_latest.json
Priority: 🔴 immediate alert for all.
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
OUTPUT_FILE = SCRIPT_DIR / "data" / "competition_latest.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")
SESSION     = requests.Session()
SESSION.headers.update({"User-Agent": "ScientificMonitor/1.0 (t.kislev@stardust-initiative.com)"})

sys.path.insert(0, str(SCRIPT_DIR))
from config import TRACKED_ORGS


def _s2_search(query: str, limit: int = 10) -> list[dict]:
    """Semantic Scholar paper search."""
    fields = "paperId,title,authors,abstract,year,publicationDate,externalIds,openAccessPdf"
    try:
        r = SESSION.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": query, "fields": fields, "limit": limit},
            timeout=15,
        )
        return r.json().get("data", [])
    except Exception as exc:
        print(f"    S2 error: {exc}")
        return []


def _arxiv_search(query: str, max_results: int = 8) -> list[dict]:
    """arXiv search."""
    params = {
        "search_query": f"all:{quote_plus(query)}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        r = SESSION.get("https://export.arxiv.org/api/query", params=params, timeout=15)
        r.raise_for_status()
    except Exception as exc:
        print(f"    arXiv error: {exc}")
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
        arxiv_id = (entry.findtext("atom:id", "", ns) or "").split("/abs/")[-1].strip()
        title    = (entry.findtext("atom:title", "", ns) or "").replace("\n", " ").strip()
        abstract = (entry.findtext("atom:summary", "", ns) or "").replace("\n", " ").strip()
        authors  = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
        results.append({
            "_type": "arxiv",
            "arxiv_id": arxiv_id,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "pub_date": pub_date,
        })
    return results


def _s2_to_paper(paper: dict, org_name: str, matched_person: str) -> dict:
    ext      = paper.get("externalIds") or {}
    doi      = ext.get("DOI", "")
    arxiv_id = ext.get("ArXiv", "")
    pub_date = (paper.get("publicationDate") or f"{paper.get('year', '')}-01-01")[:10]
    url_val  = (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id
                else f"https://doi.org/{doi}" if doi
                else f"https://www.semanticscholar.org/paper/{paper.get('paperId','')}")
    oap = paper.get("openAccessPdf") or {}
    return {
        "id":               f"s2:{paper.get('paperId','')}",
        "title":            paper.get("title") or "",
        "authors":          [a["name"] for a in paper.get("authors", [])],
        "abstract":         (paper.get("abstract") or "")[:1200],
        "url":              url_val,
        "doi":              doi,
        "published_date":   pub_date,
        "source":           "semantic_scholar",
        "pdf_url":          oap.get("url", ""),
        "is_open_access":   bool(oap),
        "category":         "competition",
        "alert_level":      "immediate",
        "tracked_author":   matched_person,
        "tracked_org":      org_name,
        "relevance_score":  9,
        "saved":            False,
        "found_at":         datetime.now(ISRAEL_TZ).isoformat(),
        "keywords_matched": [],
        "contradicts_stardust": False,
        "contradiction_details": "",
    }


def _arxiv_to_paper(paper: dict, org_name: str, matched_person: str) -> dict:
    arxiv_id = paper["arxiv_id"]
    return {
        "id":               f"arxiv:{arxiv_id}",
        "title":            paper["title"],
        "authors":          paper["authors"],
        "abstract":         paper["abstract"][:1200],
        "url":              f"https://arxiv.org/abs/{arxiv_id}",
        "doi":              "",
        "published_date":   paper["pub_date"],
        "source":           "arxiv",
        "pdf_url":          f"https://arxiv.org/pdf/{arxiv_id}",
        "is_open_access":   True,
        "category":         "competition",
        "alert_level":      "immediate",
        "tracked_author":   matched_person,
        "tracked_org":      org_name,
        "relevance_score":  9,
        "saved":            False,
        "found_at":         datetime.now(ISRAEL_TZ).isoformat(),
        "keywords_matched": [],
        "contradicts_stardust": False,
        "contradiction_details": "",
    }


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[עוקב תחרות] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    all_papers: list[dict] = []
    by_org: dict = {}

    for org in TRACKED_ORGS:
        org_name = org["name"]
        print(f"  {org_name}...")
        org_papers = []

        for term in org.get("search_terms", []):
            s2_results = _s2_search(term, 8)
            time.sleep(1)
            for r in s2_results:
                # Check if any key person matches author list
                authors_str = " ".join(a["name"] for a in r.get("authors", []))
                matched = next((p for p in org.get("key_people", []) if p.lower() in authors_str.lower()),
                               org_name)
                org_papers.append(_s2_to_paper(r, org_name, matched))

            ax_results = _arxiv_search(term, 5)
            time.sleep(1)
            for r in ax_results:
                authors_str = " ".join(r["authors"])
                matched = next((p for p in org.get("key_people", []) if p.lower() in authors_str.lower()),
                               org_name)
                org_papers.append(_arxiv_to_paper(r, org_name, matched))

        # Deduplicate
        seen = set()
        uniq = []
        for p in org_papers:
            norm = " ".join(p["title"].lower().split())[:80]
            if norm not in seen and p["title"]:
                seen.add(norm)
                uniq.append(p)

        by_org[org_name] = {
            "type":   org.get("type", ""),
            "count":  len(uniq),
            "papers": uniq,
        }
        all_papers.extend(uniq)

    output = {
        "generated_at":  now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso": now.isoformat(),
        "total":         len(all_papers),
        "by_org":        by_org,
        "papers":        all_papers,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {len(all_papers)} תוצאות · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
