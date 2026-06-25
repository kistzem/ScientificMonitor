#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
retraction_tracker.py — Agent 6: Retraction & correction tracker.
Monitors PubMed and CrossRef for retractions/corrections of SAI papers.
Saves: data/retractions_latest.json
"""

import argparse
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import pytz
import requests

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR  = Path(__file__).parent.resolve()
OUTPUT_FILE = SCRIPT_DIR / "data" / "retractions_latest.json"
PREV_FILE   = SCRIPT_DIR / "data" / "retractions_prev.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")
SESSION     = requests.Session()
SESSION.headers.update({"User-Agent": "ScientificMonitor/1.0 (t.kislev@stardust-initiative.com)"})

sys.path.insert(0, str(SCRIPT_DIR))
from config import PUBMED_EMAIL, SAI_KEYWORDS


def _search_pubmed_retractions() -> list[dict]:
    """Search PubMed for retracted SAI papers."""
    base  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    query = "(stratospheric aerosol injection OR solar radiation management OR SAI geoengineering) AND (retracted publication[pt] OR retraction of publication[pt] OR published erratum[pt])"
    try:
        r = SESSION.get(f"{base}/esearch.fcgi", params={
            "db": "pubmed", "term": query, "retmax": 50,
            "retmode": "json", "email": PUBMED_EMAIL,
        }, timeout=20)
        ids = r.json().get("esearchresult", {}).get("idlist", [])
    except Exception as exc:
        print(f"  PubMed retractions error: {exc}")
        return []
    if not ids:
        return []

    time.sleep(0.35)
    try:
        r2 = SESSION.get(f"{base}/esummary.fcgi", params={
            "db": "pubmed", "id": ",".join(ids),
            "retmode": "json", "email": PUBMED_EMAIL,
        }, timeout=20)
        summary = r2.json().get("result", {})
    except Exception as exc:
        print(f"  PubMed fetch error: {exc}")
        return []

    results = []
    for pmid in ids:
        paper = summary.get(pmid, {})
        if not paper or pmid == "uids":
            continue
        title = paper.get("title", "")
        pub_types = [(pt.get("value", "") if isinstance(pt, dict) else str(pt)).lower()
                     for pt in paper.get("pubtype", [])]
        is_retracted  = any("retract" in pt for pt in pub_types)
        is_correction = any("erratum" in pt or "correction" in pt for pt in pub_types)
        results.append({
            "id":           f"pmid:{pmid}",
            "title":        title,
            "authors":      [a.get("name", "") for a in paper.get("authors", [])],
            "url":          f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            "published":    paper.get("pubdate", "")[:10],
            "is_retracted": is_retracted,
            "is_correction": is_correction,
            "pub_types":    pub_types,
            "found_at":     datetime.now(ISRAEL_TZ).isoformat(),
        })
    return results


def _search_crossref_retractions() -> list[dict]:
    """Search CrossRef for retracted SAI papers."""
    results = []
    for q in ["stratospheric aerosol injection retraction", "solar radiation management erratum"]:
        try:
            r = SESSION.get("https://api.crossref.org/works", params={
                "query": q,
                "filter": "type:retraction,type:correction",
                "rows": 20,
                "select": "DOI,title,author,published,URL,type",
            }, timeout=20)
            items = r.json().get("message", {}).get("items", [])
        except Exception as exc:
            print(f"  CrossRef error: {exc}")
            continue

        for item in items:
            title   = " ".join(item.get("title", []))
            authors = [f"{a.get('given','')} {a.get('family','')}".strip()
                       for a in item.get("author", [])]
            pub     = item.get("published", {}).get("date-parts", [[""]])[0]
            pub_date = "-".join(str(x).zfill(2) for x in pub if x) if pub else ""
            doi     = item.get("DOI", "")
            results.append({
                "id":            f"doi:{doi}",
                "title":         title,
                "authors":       authors,
                "url":           item.get("URL", f"https://doi.org/{doi}"),
                "doi":           doi,
                "published":     pub_date[:10],
                "item_type":     item.get("type", ""),
                "is_retracted":  item.get("type") == "retraction",
                "is_correction": item.get("type") == "correction",
                "found_at":      datetime.now(ISRAEL_TZ).isoformat(),
            })
        time.sleep(0.5)
    return results


def _check_tracked_author_retractions(retractions: list[dict]) -> list[dict]:
    """Check if any tracked authors have retracted papers."""
    try:
        acad_data = json.loads((SCRIPT_DIR / "data" / "academics_latest.json")
                               .read_text(encoding="utf-8"))
        all_papers = acad_data.get("papers", [])
    except Exception:
        all_papers = []

    paper_ids = {p["id"] for p in all_papers}
    alerts = []
    for r in retractions:
        if r["id"] in paper_ids:
            alerts.append({
                "type":   "tracked_author_retraction",
                "paper":  r,
                "msg_he": f"⚠️ מאמר של חוקר מעוקב נמשך: {r['title'][:80]}",
            })
    return alerts


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[מעקב מחברים ורטרקשן] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    # Load previous retractions
    prev_ids = set()
    if PREV_FILE.exists():
        try:
            prev = json.loads(PREV_FILE.read_text(encoding="utf-8"))
            prev_ids = set(r["id"] for r in prev.get("retractions", []))
        except Exception:
            pass

    print("  PubMed retractions...")
    pm_retr = _search_pubmed_retractions()
    time.sleep(1)
    print("  CrossRef retractions...")
    cr_retr = _search_crossref_retractions()

    all_retr = pm_retr + cr_retr
    # Deduplicate
    seen = set()
    uniq = []
    for r in all_retr:
        if r["id"] not in seen:
            seen.add(r["id"])
            uniq.append(r)

    new_retractions = [r for r in uniq if r["id"] not in prev_ids]
    tracked_alerts  = _check_tracked_author_retractions(uniq)

    output = {
        "generated_at":      now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso":     now.isoformat(),
        "total":             len(uniq),
        "new_count":         len(new_retractions),
        "retractions":       uniq,
        "new_retractions":   new_retractions,
        "tracked_alerts":    tracked_alerts,
        "retracted_ids":     [r["id"] for r in uniq if r.get("is_retracted")],
        "corrected_ids":     [r["id"] for r in uniq if r.get("is_correction")],
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    PREV_FILE.write_text(json.dumps({"retractions": uniq}, ensure_ascii=False), encoding="utf-8")

    print(f"  → {len(uniq)} ({len(new_retractions)} חדשים) · {len(tracked_alerts)} התראות · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
