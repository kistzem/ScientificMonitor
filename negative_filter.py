#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
negative_filter.py — Agent 7: Negative scenario filter.
Detects papers showing negative SAI outcomes, potential damage to Stardust's reputation,
or threatening findings for the SAI field.
Saves: data/negatives_latest.json
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
OUTPUT_FILE = SCRIPT_DIR / "data" / "negatives_latest.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")
SESSION     = requests.Session()
SESSION.headers.update({"User-Agent": "ScientificMonitor/1.0 (t.kislev@stardust-initiative.com)"})

sys.path.insert(0, str(SCRIPT_DIR))
from config import NEGATIVE_TRIGGERS, CONTRADICTION_TRIGGERS


RISK_CATEGORIES = {
    "ozone_risk": {
        "keywords": ["ozone depletion stratospheric aerosol", "ozone hole aerosol injection",
                     "heterogeneous ozone loss", "chlorine activation aerosol"],
        "label_he": "סיכון לדלדול אוזון",
        "severity": "high",
    },
    "termination_shock": {
        "keywords": ["termination shock SAI", "geoengineering termination rapid warming",
                     "sudden stop stratospheric aerosol"],
        "label_he": "הלם הפסקה (Termination Shock)",
        "severity": "high",
    },
    "regional_impacts": {
        "keywords": ["SAI monsoon disruption", "geoengineering precipitation Africa",
                     "stratospheric aerosol drought", "SAI food security"],
        "label_he": "השפעות אזוריות שליליות",
        "severity": "medium",
    },
    "governance": {
        "keywords": ["geoengineering governance ban", "SAI moratorium", "stratospheric aerosol prohibited",
                     "unilateral geoengineering dangerous"],
        "label_he": "ממשל / חקיקה נגד SAI",
        "severity": "medium",
    },
    "stardust_threat": {
        "keywords": ["startup geoengineering reckless", "commercial SAI dangerous",
                     "private geoengineering experiment harmful", "unauthorized aerosol release"],
        "label_he": "איום על חברות SAI פרטיות",
        "severity": "critical",
    },
}


def _load_all_papers() -> list[dict]:
    papers = []
    for fname in ["papers_latest.json", "academics_latest.json", "competition_latest.json"]:
        fpath = SCRIPT_DIR / "data" / fname
        if not fpath.exists():
            continue
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            papers.extend(data.get("papers", []))
        except Exception:
            pass
    return papers


def _search_semantic_scholar_negative(query: str, limit: int = 10) -> list[dict]:
    """Search for negative SAI papers."""
    fields = "paperId,title,authors,abstract,year,publicationDate,externalIds,openAccessPdf"
    try:
        r = SESSION.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": query, "fields": fields, "limit": limit},
            timeout=15,
        )
        return r.json().get("data", [])
    except Exception as exc:
        print(f"  S2 error ({query[:40]}): {exc}")
        return []


def _classify_risk(title: str, abstract: str) -> list[dict]:
    """Classify which risk categories apply to this paper."""
    text     = (title + " " + abstract).lower()
    matched  = []
    for risk_key, risk in RISK_CATEGORIES.items():
        if any(kw.lower() in text for kw in risk["keywords"]):
            matched.append({
                "risk_key":  risk_key,
                "label_he":  risk["label_he"],
                "severity":  risk["severity"],
            })
    return matched


def _to_finding(paper_data: dict, risks: list[dict], source_query: str) -> dict:
    ext      = paper_data.get("externalIds") or {}
    doi      = ext.get("DOI", "")
    arxiv_id = ext.get("ArXiv", "")
    pub_date = (paper_data.get("publicationDate") or f"{paper_data.get('year','')}-01-01")[:10]
    url_val  = (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id
                else f"https://doi.org/{doi}" if doi
                else f"https://www.semanticscholar.org/paper/{paper_data.get('paperId','')}")
    oap      = paper_data.get("openAccessPdf") or {}
    severity = max((r["severity"] for r in risks), key=lambda s: {"critical":3,"high":2,"medium":1,"low":0}.get(s,0), default="medium")
    return {
        "id":             f"s2:{paper_data.get('paperId','')}",
        "title":          paper_data.get("title") or "",
        "authors":        [a["name"] for a in paper_data.get("authors", [])],
        "abstract":       (paper_data.get("abstract") or "")[:1200],
        "url":            url_val,
        "doi":            doi,
        "published_date": pub_date,
        "source":         "semantic_scholar",
        "pdf_url":        oap.get("url", ""),
        "is_open_access": bool(oap),
        "risk_categories": risks,
        "severity":       severity,
        "search_query":   source_query,
        "found_at":       datetime.now(ISRAEL_TZ).isoformat(),
    }


def _scan_existing_papers(all_papers: list[dict]) -> list[dict]:
    """Scan already-fetched papers for negative findings."""
    negatives = []
    for p in all_papers:
        risks = _classify_risk(p.get("title", ""), p.get("abstract", ""))
        if risks:
            severity = max((r["severity"] for r in risks),
                           key=lambda s: {"critical":3,"high":2,"medium":1,"low":0}.get(s,0),
                           default="medium")
            neg_p = dict(p)
            neg_p["risk_categories"] = risks
            neg_p["severity"]        = severity
            negatives.append(neg_p)
    return negatives


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[סינון תרחישים שליליים] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    # 1. Scan existing papers
    all_papers  = _load_all_papers()
    existing_neg = _scan_existing_papers(all_papers)
    print(f"  {len(existing_neg)} שליליים בקובצי קיימים")

    # 2. Targeted negative searches
    new_findings: list[dict] = []
    negative_queries = [
        "stratospheric aerosol injection ozone depletion risk",
        "SAI geoengineering harmful effects",
        "solar radiation management termination shock",
        "geoengineering governance ban prohibited",
        "private stratospheric aerosol experiment danger",
    ]
    for q in negative_queries:
        results = _search_semantic_scholar_negative(q, 8)
        time.sleep(1)
        for paper_data in results:
            risks = _classify_risk(
                paper_data.get("title") or "",
                paper_data.get("abstract") or "",
            )
            if risks:
                new_findings.append(_to_finding(paper_data, risks, q))

    # Combine and deduplicate
    all_neg = existing_neg + new_findings
    seen = set()
    uniq = []
    for n in all_neg:
        norm = " ".join(n.get("title", "").lower().split())[:80]
        if norm and norm not in seen:
            seen.add(norm)
            uniq.append(n)

    # Sort by severity
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    uniq.sort(key=lambda n: sev_order.get(n.get("severity", "low"), 3))

    critical = [n for n in uniq if n.get("severity") == "critical"]
    high     = [n for n in uniq if n.get("severity") == "high"]

    output = {
        "generated_at":   now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso":  now.isoformat(),
        "total":          len(uniq),
        "critical_count": len(critical),
        "high_count":     len(high),
        "findings":       uniq,
        "critical":       critical,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {len(uniq)} ממצאים ({len(critical)} קריטי, {len(high)} גבוה) · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
