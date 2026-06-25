#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
funding_tracker.py — Agent 8: Funding intelligence.
Tracks grants, funding sources, and opportunities in SAI/SRM field.
Saves: data/funding_latest.json
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
OUTPUT_FILE = SCRIPT_DIR / "data" / "funding_latest.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")
SESSION     = requests.Session()
SESSION.headers.update({"User-Agent": "ScientificMonitor/1.0 (t.kislev@stardust-initiative.com)"})

sys.path.insert(0, str(SCRIPT_DIR))
from config import SAI_FUNDERS


def _crossref_with_funding(query: str, limit: int = 20) -> list[dict]:
    """Find papers with explicit funding information via CrossRef."""
    try:
        r = SESSION.get("https://api.crossref.org/works", params={
            "query": query,
            "filter": "has-funder:true",
            "rows": limit,
            "sort": "published",
            "order": "desc",
            "select": "DOI,title,author,published,funder,URL,abstract",
        }, timeout=20)
        items = r.json().get("message", {}).get("items", [])
    except Exception as exc:
        print(f"  CrossRef error: {exc}")
        return []

    results = []
    for item in items:
        title   = " ".join(item.get("title", []))
        funders = [f.get("name", "") for f in item.get("funder", [])]
        if not any(any(sf.lower() in f.lower() for sf in SAI_FUNDERS) for f in funders):
            if not any(sf.lower() in title.lower() for sf in ["stratospheric", "SAI", "geoengineering", "aerosol injection"]):
                continue

        authors = [f"{a.get('given','')} {a.get('family','')}".strip()
                   for a in item.get("author", [])]
        pub     = item.get("published", {}).get("date-parts", [[""]])[0]
        pub_date = "-".join(str(x).zfill(2) for x in pub if x)[:10] if pub else ""
        doi     = item.get("DOI", "")
        results.append({
            "id":            f"doi:{doi}",
            "title":         title,
            "authors":       authors[:5],
            "funders":       funders,
            "doi":           doi,
            "url":           item.get("URL", f"https://doi.org/{doi}"),
            "published_date": pub_date,
            "source":        "crossref",
            "amount_usd":    None,
            "funder_type":   _classify_funder(funders),
            "found_at":      datetime.now(ISRAEL_TZ).isoformat(),
        })
    return results


def _semantic_scholar_funding(query: str, limit: int = 15) -> list[dict]:
    """Find SAI papers and extract any funding info from abstracts."""
    fields = "paperId,title,authors,abstract,year,publicationDate,externalIds,publicationVenue"
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
    cutoff = (datetime.now(ISRAEL_TZ) - timedelta(days=180)).strftime("%Y-%m-%d")
    for paper in data:
        abstract = paper.get("abstract") or ""
        title    = paper.get("title") or ""
        text     = (title + " " + abstract).lower()
        # Check if abstract mentions funding
        if not any(f.lower() in text for f in
                   ["funded by", "supported by", "grant", "fellowship", "award", "funding"]):
            continue
        ext      = paper.get("externalIds") or {}
        doi      = ext.get("DOI", "")
        arxiv_id = ext.get("ArXiv", "")
        pub_date = (paper.get("publicationDate") or "")[:10]
        if pub_date < cutoff:
            continue
        url_val  = (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id
                    else f"https://doi.org/{doi}" if doi
                    else f"https://www.semanticscholar.org/paper/{paper.get('paperId','')}")

        # Extract funder mentions from abstract
        funders_found = [f for f in SAI_FUNDERS if f.lower() in text]
        results.append({
            "id":            f"s2:{paper.get('paperId','')}",
            "title":         title,
            "authors":       [a["name"] for a in paper.get("authors", [])][:5],
            "funders":       funders_found or ["לא צוין"],
            "doi":           doi,
            "url":           url_val,
            "published_date": pub_date,
            "source":        "semantic_scholar",
            "amount_usd":    None,
            "funder_type":   _classify_funder(funders_found),
            "found_at":      datetime.now(ISRAEL_TZ).isoformat(),
        })
    return results


def _classify_funder(funders: list[str]) -> str:
    govt_keywords  = ["NSF", "DOE", "NASA", "NOAA", "Department", "National Science", "European Research"]
    priv_keywords  = ["Foundation", "Open Philanthropy", "Grantham", "Fund for Innovative"]
    funder_str     = " ".join(funders)
    if any(k.lower() in funder_str.lower() for k in govt_keywords):
        return "government"
    if any(k.lower() in funder_str.lower() for k in priv_keywords):
        return "private"
    return "unknown"


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[Funding Intelligence] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    all_funding: list[dict] = []
    for q in ["stratospheric aerosol injection funding", "solar radiation management grant",
               "geoengineering NSF award"]:
        print(f"  CrossRef: {q[:40]}...")
        all_funding += _crossref_with_funding(q, 15)
        time.sleep(1)
        print(f"  S2: {q[:40]}...")
        all_funding += _semantic_scholar_funding(q, 10)
        time.sleep(1)

    # Deduplicate
    seen = set()
    uniq = []
    for f in all_funding:
        norm = " ".join(f.get("title", "").lower().split())[:80]
        if norm and norm not in seen:
            seen.add(norm)
            uniq.append(f)

    by_type = {"government": [], "private": [], "unknown": []}
    for f in uniq:
        by_type.setdefault(f.get("funder_type", "unknown"), []).append(f)

    output = {
        "generated_at":   now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso":  now.isoformat(),
        "total":          len(uniq),
        "by_type":        {k: len(v) for k, v in by_type.items()},
        "items":          uniq,
        "by_funder_type": by_type,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {len(uniq)} רשומות מימון · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
