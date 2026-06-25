#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
policy_monitor.py — Agent 11: Policy monitor.
Tracks government statements, regulations, and international agreements on SAI/SRM.
Saves: data/policy_latest.json
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
OUTPUT_FILE = SCRIPT_DIR / "data" / "policy_latest.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")
SESSION     = requests.Session()
SESSION.headers.update({"User-Agent": "ScientificMonitor/1.0 (t.kislev@stardust-initiative.com)"})

POLICY_QUERIES = [
    "solar radiation management policy regulation",
    "stratospheric aerosol injection governance international",
    "geoengineering legislation ban moratorium",
    "SRM UNEP United Nations geoengineering",
    "SAI environmental impact assessment law",
    "climate intervention regulatory framework",
]

RISK_SIGNALS = ["ban", "prohibit", "moratorium", "illegal", "sanction", "restrict",
                "dangerous", "unilateral", "liability", "criminal"]

OPPORTUNITY_SIGNALS = ["permit", "authorize", "approve", "fund", "support", "encourage",
                        "framework", "assessment", "research", "pilot"]


def _s2_policy_search(query: str, limit: int = 12) -> list[dict]:
    fields = "paperId,title,authors,abstract,year,publicationDate,externalIds,openAccessPdf"
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
    cutoff  = (datetime.now(ISRAEL_TZ) - timedelta(days=365)).strftime("%Y-%m-%d")
    for paper in data:
        pub_date = (paper.get("publicationDate") or "")[:10]
        if pub_date and pub_date < cutoff:
            continue
        title    = paper.get("title") or ""
        abstract = paper.get("abstract") or ""
        # Must be policy-related
        text     = (title + " " + abstract).lower()
        if not any(kw in text for kw in ["policy", "governance", "regulat", "legislat", "law",
                                          "treaty", "agreement", "united nations", "UNEP",
                                          "ban", "prohibit", "moratorium", "framework"]):
            continue
        ext      = paper.get("externalIds") or {}
        doi      = ext.get("DOI", "")
        arxiv_id = ext.get("ArXiv", "")
        url_val  = (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id
                    else f"https://doi.org/{doi}" if doi
                    else f"https://www.semanticscholar.org/paper/{paper.get('paperId','')}")
        oap = paper.get("openAccessPdf") or {}
        risk_level = "high" if any(s in text for s in RISK_SIGNALS) else \
                     "opportunity" if any(s in text for s in OPPORTUNITY_SIGNALS) else "neutral"
        results.append({
            "id":             f"s2:{paper.get('paperId','')}",
            "title":          title,
            "authors":        [a["name"] for a in paper.get("authors", [])][:5],
            "abstract":       abstract[:1000],
            "url":            url_val,
            "doi":            doi,
            "published_date": pub_date,
            "source":         "semantic_scholar",
            "pdf_url":        oap.get("url", ""),
            "is_open_access": bool(oap),
            "category":       "policy",
            "risk_level":     risk_level,
            "alert_level":    "immediate" if risk_level == "high" else "daily",
            "saved":          False,
            "found_at":       datetime.now(ISRAEL_TZ).isoformat(),
            "keywords_matched": [],
            "tracked_author": None,
            "tracked_org":    None,
            "relevance_score": 8 if risk_level == "high" else 6,
            "contradicts_stardust": False,
            "contradiction_details": "",
        })
    return results


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[Policy Monitor] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    all_items: list[dict] = []
    for q in POLICY_QUERIES:
        print(f"  {q[:45]}...")
        all_items += _s2_policy_search(q, 12)
        time.sleep(1)

    # Deduplicate
    seen = set()
    uniq = []
    for p in all_items:
        norm = " ".join(p.get("title", "").lower().split())[:80]
        if norm and norm not in seen:
            seen.add(norm)
            uniq.append(p)

    risks  = [p for p in uniq if p.get("risk_level") == "high"]
    opps   = [p for p in uniq if p.get("risk_level") == "opportunity"]

    output = {
        "generated_at":    now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso":   now.isoformat(),
        "total":           len(uniq),
        "risk_count":      len(risks),
        "opportunity_count": len(opps),
        "items":           uniq,
        "risks":           risks,
        "opportunities":   opps,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {len(uniq)} פריטי מדיניות ({len(risks)} סיכון, {len(opps)} הזדמנות) · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
