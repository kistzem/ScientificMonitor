#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
field_tracker.py — Agent 1: Field tracker.
Searches arXiv, PubMed, Semantic Scholar, CrossRef, Google Patents for SAI/SRM papers.
Saves: data/papers_latest.json
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
OUTPUT_FILE = SCRIPT_DIR / "data" / "papers_latest.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")
SESSION     = requests.Session()
SESSION.headers.update({"User-Agent": "ScientificMonitor/1.0 (t.kislev@stardust-initiative.com)"})

sys.path.insert(0, str(SCRIPT_DIR))
from config import SAI_KEYWORDS, EXCLUDE_KEYWORDS, PUBMED_EMAIL


def _make_paper(source: str, paper_id: str, title: str, authors: list,
                abstract: str, url: str, doi: str, pub_date: str,
                pdf_url: str = "", is_open: bool = False) -> dict:
    return {
        "id":           paper_id,
        "title":        title.strip(),
        "authors":      authors,
        "abstract":     (abstract or "").strip()[:1200],
        "url":          url,
        "doi":          doi or "",
        "published_date": pub_date,
        "source":       source,
        "pdf_url":      pdf_url,
        "is_open_access": is_open,
        "keywords_matched": [],
        "category":     "field",
        "relevance_score": 0,
        "alert_level":  "none",
        "tracked_author": None,
        "tracked_org":  None,
        "contradicts_stardust": False,
        "contradiction_details": "",
        "saved":        False,
        "found_at":     datetime.now(ISRAEL_TZ).isoformat(),
    }


def _is_relevant(title: str, abstract: str) -> list[str]:
    """Return matched SAI keywords; empty list if excluded."""
    text = (title + " " + abstract).lower()
    for excl in EXCLUDE_KEYWORDS:
        if excl.lower() in text:
            return []
    matched = [kw for kw in SAI_KEYWORDS if kw.lower() in text]
    return matched


def _search_arxiv(query: str, max_results: int = 25) -> list[dict]:
    """Search arXiv via Atom API."""
    url = "https://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{quote_plus(query)}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        r = SESSION.get(url, params=params, timeout=20)
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
    for entry in root.findall("atom:entry", ns):
        title    = (entry.findtext("atom:title", "", ns) or "").replace("\n", " ").strip()
        abstract = (entry.findtext("atom:summary", "", ns) or "").replace("\n", " ").strip()
        matched  = _is_relevant(title, abstract)
        if not matched:
            continue

        arxiv_id = (entry.findtext("atom:id", "", ns) or "").split("/abs/")[-1].strip()
        authors  = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
        pub_raw  = entry.findtext("atom:published", "", ns) or ""
        pub_date = pub_raw[:10] if pub_raw else ""
        doi_el   = entry.find(".//{http://arxiv.org/schemas/atom}doi")
        doi      = doi_el.text if doi_el is not None else ""
        pdf_url  = f"https://arxiv.org/pdf/{arxiv_id}"
        p = _make_paper("arxiv", f"arxiv:{arxiv_id}", title, authors, abstract,
                        f"https://arxiv.org/abs/{arxiv_id}", doi, pub_date, pdf_url, True)
        p["keywords_matched"] = matched
        results.append(p)
    return results


def _search_pubmed(query: str, max_results: int = 20) -> list[dict]:
    """Search PubMed via E-utilities."""
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    try:
        r = SESSION.get(f"{base}/esearch.fcgi", params={
            "db": "pubmed", "term": query, "retmax": max_results,
            "retmode": "json", "sort": "pub date",
            "email": PUBMED_EMAIL,
        }, timeout=20)
        ids = r.json().get("esearchresult", {}).get("idlist", [])
    except Exception as exc:
        print(f"  PubMed search error: {exc}")
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
        title    = paper.get("title", "")
        abstract = ""
        authors  = [a.get("name", "") for a in paper.get("authors", [])]
        pub_date = paper.get("pubdate", "")[:10]
        doi      = next((el.get("value", "") for el in paper.get("elocationid", [])
                         if isinstance(el, dict) and el.get("etype") == "doi"), "")
        url      = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        matched  = _is_relevant(title, abstract)
        if not matched and not any(kw.lower() in title.lower() for kw in SAI_KEYWORDS[:3]):
            continue
        p = _make_paper("pubmed", f"pmid:{pmid}", title, authors, abstract, url, doi, pub_date)
        p["keywords_matched"] = matched or [SAI_KEYWORDS[0]]
        results.append(p)
    return results


def _search_semantic_scholar(query: str, max_results: int = 25) -> list[dict]:
    """Search Semantic Scholar Graph API."""
    url    = "https://api.semanticscholar.org/graph/v1/paper/search"
    fields = "paperId,title,authors,abstract,year,publicationDate,externalIds,openAccessPdf"
    try:
        r = SESSION.get(url, params={"query": query, "fields": fields,
                                      "limit": min(max_results, 100)}, timeout=20)
        data = r.json().get("data", [])
    except Exception as exc:
        print(f"  S2 error: {exc}")
        return []

    results = []
    for paper in data:
        title    = paper.get("title") or ""
        abstract = paper.get("abstract") or ""
        matched  = _is_relevant(title, abstract)
        if not matched:
            continue
        authors  = [a["name"] for a in paper.get("authors", [])]
        ext      = paper.get("externalIds") or {}
        doi      = ext.get("DOI", "")
        arxiv_id = ext.get("ArXiv", "")
        pub_date = paper.get("publicationDate") or f"{paper.get('year', '')}-01-01"
        url_val  = (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id
                    else f"https://doi.org/{doi}" if doi
                    else f"https://www.semanticscholar.org/paper/{paper.get('paperId', '')}")
        oap      = paper.get("openAccessPdf") or {}
        p = _make_paper("semantic_scholar", f"s2:{paper.get('paperId','')}", title, authors,
                        abstract, url_val, doi, str(pub_date)[:10], oap.get("url", ""), bool(oap))
        p["keywords_matched"] = matched
        results.append(p)
    return results


def _search_patents(query: str, max_results: int = 15) -> list[dict]:
    """Search Google Patents via RSS feed."""
    url = f"https://patents.google.com/xhr/query?url=q%3D{quote_plus(query)}&exp=&download=false"
    try:
        r = SESSION.get(url, timeout=20,
                        headers={"Accept": "application/json"})
        data = r.json()
        hits = data.get("results", {}).get("cluster", [])
        if not hits:
            return []
    except Exception:
        return []

    results = []
    for cluster in hits[:max_results]:
        for item in cluster.get("result", []):
            pat = item.get("patent", {})
            title  = pat.get("title", "")
            abs_   = pat.get("abstract", "")
            matched = _is_relevant(title, abs_)
            if not matched:
                continue
            pat_id = pat.get("publication_number", "")
            pub_date = (pat.get("publication_date") or {}).get("raw", "")[:10]
            inventors = [inv.get("name", "") for inv in pat.get("inventor", [])]
            url_p = f"https://patents.google.com/patent/{pat_id}"
            p = _make_paper("patent", f"patent:{pat_id}", title, inventors, abs_,
                            url_p, "", pub_date)
            p["category"]         = "patent"
            p["keywords_matched"] = matched
            results.append(p)
    return results


def _deduplicate(papers: list[dict]) -> list[dict]:
    """Deduplicate by DOI then by normalized title."""
    seen_doi   = set()
    seen_title = set()
    out = []
    for p in papers:
        doi = p.get("doi", "").lower().strip()
        norm_title = " ".join(p["title"].lower().split())[:80]
        if doi and doi in seen_doi:
            continue
        if norm_title in seen_title:
            continue
        if doi:
            seen_doi.add(doi)
        seen_title.add(norm_title)
        out.append(p)
    return out


def run() -> list[dict]:
    now = datetime.now(ISRAEL_TZ)
    print(f"[עוקב תחום] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    all_papers: list[dict] = []
    primary_queries = [
        "stratospheric aerosol injection",
        "heterogeneous uptake aerosol stratosphere",
        "CaCO3 SiO2 stratosphere geoengineering",
        "ozone polar stratospheric cloud chemistry",
        "solar radiation management aerosol",
    ]

    for i, q in enumerate(primary_queries):
        print(f"  arXiv: {q[:50]}...")
        all_papers += _search_arxiv(q, 20)
        time.sleep(2)
        print(f"  S2: {q[:50]}...")
        all_papers += _search_semantic_scholar(q, 15)
        time.sleep(1)
        if i % 2 == 0:
            print(f"  PubMed: {q[:50]}...")
            all_papers += _search_pubmed(q, 15)
            time.sleep(0.5)

    print(f"  Patents search...")
    all_papers += _search_patents("stratospheric aerosol injection geoengineering", 10)

    unique = _deduplicate(all_papers)

    # Date-filter: last 90 days
    cutoff = (datetime.now(ISRAEL_TZ) - timedelta(days=90)).strftime("%Y-%m-%d")
    recent = [p for p in unique if p["published_date"] >= cutoff or not p["published_date"]]

    output = {
        "generated_at": now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso": now.isoformat(),
        "total": len(recent),
        "papers": recent,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {len(recent)} מאמרים · נשמר: {OUTPUT_FILE.name}")
    return recent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
