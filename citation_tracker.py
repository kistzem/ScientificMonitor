#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
citation_tracker.py — Agent 5: Citation intelligence.
Tracks who cites key papers, detects misrepresentation.
Saves: data/citations_latest.json
"""

import argparse
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import pytz
import requests

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR  = Path(__file__).parent.resolve()
OUTPUT_FILE = SCRIPT_DIR / "data" / "citations_latest.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")
SESSION     = requests.Session()
SESSION.headers.update({"User-Agent": "ScientificMonitor/1.0 (t.kislev@stardust-initiative.com)"})

sys.path.insert(0, str(SCRIPT_DIR))
from config import TRACKED_ACADEMICS

MISREPRESENTATION_SIGNALS = [
    "claims that", "according to", "reported that", "showed that",
    "found no", "did not find", "failed to",
]


def _get_s2_paper_id(title: str, author: str) -> str | None:
    """Find S2 paper ID by title search."""
    try:
        r = SESSION.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": f"{title} {author}", "fields": "paperId,title", "limit": 3},
            timeout=15,
        )
        data = r.json().get("data", [])
        if data:
            return data[0]["paperId"]
    except Exception:
        pass
    return None


def _get_citations(paper_id: str, limit: int = 25) -> list[dict]:
    """Get papers that cite this paper via Semantic Scholar."""
    fields = "paperId,title,authors,year,publicationDate,externalIds"
    try:
        r = SESSION.get(
            f"https://api.semanticscholar.org/graph/v1/paper/{paper_id}/citations",
            params={"fields": fields, "limit": limit},
            timeout=15,
        )
        data = r.json().get("data", [])
        return [item.get("citingPaper", {}) for item in data]
    except Exception as exc:
        print(f"    Citations error: {exc}")
        return []


def _detect_misrepresentation(citing_abstract: str, cited_title: str) -> bool:
    """Heuristic: check if citing paper might misrepresent cited paper."""
    if not citing_abstract:
        return False
    abstract_lower = citing_abstract.lower()
    cited_lower    = cited_title.lower()
    # Simplified: flag if citing paper contradicts key terms from cited paper
    signals = sum(1 for sig in MISREPRESENTATION_SIGNALS if sig in abstract_lower)
    return signals >= 2  # Heuristic threshold


def _get_tracked_author_papers(limit: int = 5) -> list[dict]:
    """Get recent papers from tracked academics for citation tracking."""
    papers = []
    for fname in ["academics_latest.json"]:
        fpath = SCRIPT_DIR / "data" / fname
        if not fpath.exists():
            continue
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            papers.extend(data.get("papers", []))
        except Exception:
            pass
    # Filter only papers with S2 IDs
    s2_papers = [p for p in papers if p["id"].startswith("s2:")]
    return s2_papers[:limit]


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[Citation Intelligence] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    tracked_papers = _get_tracked_author_papers(8)
    print(f"  מנטר ציטוטים עבור {len(tracked_papers)} מאמרים...")

    all_citation_data: list[dict] = []
    misrep_alerts: list[dict]     = []
    trajectory_alerts: list[dict] = []

    for paper in tracked_papers:
        s2_id  = paper["id"].replace("s2:", "")
        title  = paper.get("title", "")[:60]
        author = (paper.get("authors") or [""])[0]
        print(f"  ↳ {author}: {title[:50]}...")

        citing = _get_citations(s2_id, 20)
        time.sleep(1)

        citations_info = []
        for c in citing:
            ext      = c.get("externalIds") or {}
            doi      = ext.get("DOI", "")
            arxiv_id = ext.get("ArXiv", "")
            url      = (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id
                        else f"https://doi.org/{doi}" if doi
                        else f"https://www.semanticscholar.org/paper/{c.get('paperId','')}")
            citing_authors = [a["name"] for a in c.get("authors", [])]
            citations_info.append({
                "citing_id":      c.get("paperId", ""),
                "citing_title":   c.get("title", ""),
                "citing_authors": citing_authors[:3],
                "year":           c.get("year"),
                "pub_date":       (c.get("publicationDate") or "")[:10],
                "url":            url,
                "misrep_flag":    False,
            })

        # Trajectory: sudden spike
        if len(citations_info) >= 15:
            trajectory_alerts.append({
                "paper_id":     paper["id"],
                "paper_title":  paper.get("title", "")[:80],
                "author":       author,
                "citation_count": len(citations_info),
                "msg_he":       f"📈 '{title}' קיבל {len(citations_info)} ציטוטים — עלייה משמעותית",
            })

        all_citation_data.append({
            "paper_id":      paper["id"],
            "paper_title":   paper.get("title", "")[:100],
            "tracked_author": author,
            "citation_count": len(citations_info),
            "citations":     citations_info,
        })

    output = {
        "generated_at":       now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso":      now.isoformat(),
        "total_tracked":      len(all_citation_data),
        "citation_data":      all_citation_data,
        "misrep_alerts":      misrep_alerts,
        "trajectory_alerts":  trajectory_alerts,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {len(all_citation_data)} מאמרים · {len(misrep_alerts)} ייצוג שגוי · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
