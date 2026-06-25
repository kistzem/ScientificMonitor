#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patent_landscape.py — Agent 9: Patent landscape analysis.
Maps SAI/SRM patent ownership, detects IP gaps, clusters, and disputes.
Saves: data/patents_latest.json
"""

import argparse
import io
import json
import re
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
OUTPUT_FILE = SCRIPT_DIR / "data" / "patents_latest.json"
PREV_FILE   = SCRIPT_DIR / "data" / "patents_prev.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")
SESSION     = requests.Session()
SESSION.headers.update({"User-Agent": "ScientificMonitor/1.0 (t.kislev@stardust-initiative.com)"})

sys.path.insert(0, str(SCRIPT_DIR))
from config import TRACKED_ACADEMICS, TRACKED_ORGS

# Core SAI patent queries
PATENT_QUERIES = [
    "stratospheric aerosol injection",
    "solar radiation management aerosol",
    "stratospheric geoengineering particle",
    "SRM aerosol delivery stratosphere",
    "solar geoengineering dispersion",
    "aerosol reflectivity climate intervention",
    "silica particles stratosphere climate",
]

# Known assignees to flag as competitors
COMPETITOR_ASSIGNEES = [
    "Harvard University",
    "University of Washington",
    "University of Leeds",
    "ETH Zurich",
    "Carnegie Institution",
    "NOAA",
    "NASA",
    "National Oceanic",
    "Make Sunsets",
    "Silver Lining",
    "Climate Restoration",
]

# IP domains where Stardust has potential overlap
STARDUST_IP_TERMS = [
    "silica aerosol", "SiO2 geoengineering", "heterogeneous silica stratosphere",
    "non-sulfate aerosol injection", "stratospheric particle delivery vehicle",
    "engineered aerosol particle climate",
]

# Patent clusters (technology groupings)
CLUSTER_KEYWORDS = {
    "delivery_mechanism":  ["aircraft", "balloon", "nozzle", "dispersion", "delivery", "release mechanism"],
    "particle_chemistry":  ["sulfur", "silica", "calcium", "carbonate", "aerosol composition", "particle size"],
    "monitoring":          ["lidar", "satellite", "remote sensing", "measurement", "monitoring system"],
    "governance":          ["consent", "governance", "international", "treaty", "regulatory"],
    "modeling":            ["simulation", "climate model", "radiative forcing", "feedback", "atmospheric model"],
}


def _google_patents_search(query: str, limit: int = 20) -> list[dict]:
    """Search Google Patents via their unofficial JSON endpoint."""
    results = []
    try:
        r = SESSION.get(
            "https://patents.google.com/xhr/query",
            params={
                "url": f"q={quote_plus(query)}&after=priority:20180101",
                "exp": "",
                "download": "false",
            },
            timeout=20,
        )
        data = r.json()
        patents = data.get("results", {}).get("cluster", [])
        for cluster in patents[:limit]:
            for result in cluster.get("result", []):
                p = result.get("patent", {})
                if not p:
                    continue
                patent_id   = p.get("publication_number", "")
                title       = p.get("title", "")
                assignee    = p.get("assignee_harmonized", [{}])
                assignees   = [a.get("name", "") for a in (assignee if isinstance(assignee, list) else [assignee])]
                inventors   = [i.get("name", "") for i in p.get("inventor_harmonized", [])]
                filing_date = p.get("filing_date", "")[:10] or p.get("priority_date", "")[:10]
                pub_date    = p.get("publication_date", "")[:10]
                abs_text    = p.get("abstract", "")
                results.append({
                    "id":          f"patent:{patent_id}",
                    "patent_id":   patent_id,
                    "title":       title,
                    "assignees":   assignees,
                    "inventors":   inventors,
                    "filing_date": filing_date,
                    "pub_date":    pub_date,
                    "abstract":    abs_text[:800],
                    "url":         f"https://patents.google.com/patent/{patent_id}",
                    "source":      "google_patents",
                })
    except Exception as exc:
        print(f"  Google Patents error: {exc}")
    return results


def _semantic_scholar_patents(query: str, limit: int = 15) -> list[dict]:
    """Fallback: fetch patent-adjacent publications from Semantic Scholar."""
    fields = "paperId,title,authors,abstract,year,publicationDate,externalIds,publicationVenue,openAccessPdf"
    try:
        r = SESSION.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": query + " patent", "fields": fields, "limit": limit},
            timeout=15,
        )
        data = r.json().get("data", [])
    except Exception as exc:
        print(f"  S2 error: {exc}")
        return []

    results = []
    cutoff = (datetime.now(ISRAEL_TZ) - timedelta(days=365 * 3)).strftime("%Y-%m-%d")
    for paper in data:
        pub_date = (paper.get("publicationDate") or "")[:10]
        if pub_date and pub_date < cutoff:
            continue
        title = paper.get("title") or ""
        abstract = paper.get("abstract") or ""
        text = (title + " " + abstract).lower()
        if not any(kw in text for kw in ["patent", "intellectual property", "IP", "invention", "claims"]):
            continue
        ext = paper.get("externalIds") or {}
        doi = ext.get("DOI", "")
        arxiv_id = ext.get("ArXiv", "")
        url_val = (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id
                   else f"https://doi.org/{doi}" if doi
                   else f"https://www.semanticscholar.org/paper/{paper.get('paperId','')}")
        results.append({
            "id":          f"s2:{paper.get('paperId','')}",
            "patent_id":   "",
            "title":       title,
            "assignees":   [a["name"] for a in paper.get("authors", [])][:3],
            "inventors":   [],
            "filing_date": "",
            "pub_date":    pub_date,
            "abstract":    abstract[:800],
            "url":         url_val,
            "source":      "semantic_scholar",
        })
    return results


def _classify_cluster(patent: dict) -> list[str]:
    """Assign patent to one or more technology clusters."""
    text = (patent.get("title", "") + " " + patent.get("abstract", "")).lower()
    clusters = []
    for cluster_name, keywords in CLUSTER_KEYWORDS.items():
        if any(kw.lower() in text for kw in keywords):
            clusters.append(cluster_name)
    return clusters or ["other"]


def _detect_competitor(patent: dict) -> str | None:
    """Return competitor name if patent belongs to a known competitor."""
    assignee_str = " ".join(patent.get("assignees", [])).lower()
    for comp in COMPETITOR_ASSIGNEES:
        if comp.lower() in assignee_str:
            return comp
    return None


def _check_stardust_overlap(patent: dict) -> bool:
    """Check if patent overlaps with Stardust IP terms."""
    text = (patent.get("title", "") + " " + patent.get("abstract", "")).lower()
    return any(term.lower() in text for term in STARDUST_IP_TERMS)


def _detect_tracked_inventor(patent: dict) -> str | None:
    """Check if a tracked academic appears as inventor."""
    inventors_str = " ".join(patent.get("inventors", [])).lower()
    for acad in TRACKED_ACADEMICS:
        last = acad["name"].split()[-1].lower()
        if last in inventors_str:
            return acad["name"]
    return None


def _detect_gaps(patents: list[dict]) -> list[dict]:
    """Identify technology areas with few patents — potential IP gaps."""
    cluster_counts: dict[str, int] = {k: 0 for k in CLUSTER_KEYWORDS}
    for p in patents:
        for cl in p.get("clusters", []):
            if cl in cluster_counts:
                cluster_counts[cl] += 1

    gaps = []
    for cluster, count in cluster_counts.items():
        if count < 3:
            gaps.append({
                "cluster":     cluster,
                "patent_count": count,
                "opportunity": f"פחות מ-3 פטנטים בתחום {cluster} — הזדמנות פוטנציאלית לStardust",
            })
    return gaps


def _detect_disputes(patents: list[dict]) -> list[dict]:
    """Find patents with similar scope that may conflict."""
    disputes = []
    for i, pa in enumerate(patents):
        for pb in patents[i + 1:]:
            if pa.get("source") == pb.get("source") and pa["source"] == "semantic_scholar":
                continue
            title_a = set(re.sub(r"[^a-z ]", "", pa.get("title", "").lower()).split())
            title_b = set(re.sub(r"[^a-z ]", "", pb.get("title", "").lower()).split())
            shared = title_a & title_b - {"the", "a", "an", "of", "for", "and", "in", "on"}
            if len(shared) >= 4:
                disputes.append({
                    "patent_a": pa.get("patent_id") or pa.get("id"),
                    "title_a":  pa.get("title", "")[:70],
                    "patent_b": pb.get("patent_id") or pb.get("id"),
                    "title_b":  pb.get("title", "")[:70],
                    "shared_terms": list(shared)[:6],
                    "severity": "high" if pa.get("stardust_overlap") or pb.get("stardust_overlap") else "medium",
                    "msg_he":   f"⚠️ חפיפה פוטנציאלית: {pa.get('title','')[:40]} ↔ {pb.get('title','')[:40]}",
                })
    return disputes[:10]


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[Patent Landscape] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    all_patents: list[dict] = []
    for q in PATENT_QUERIES:
        print(f"  Google Patents: {q[:45]}...")
        results = _google_patents_search(q, 15)
        all_patents.extend(results)
        time.sleep(1.5)
        if not results:
            # Fallback to S2 patent-related papers
            print(f"    (fallback S2)...")
            all_patents.extend(_semantic_scholar_patents(q, 10))
            time.sleep(1)

    # Deduplicate by patent_id then by title
    seen_ids    = set()
    seen_titles = set()
    uniq: list[dict] = []
    for p in all_patents:
        pid   = p.get("patent_id") or p.get("id")
        title = " ".join((p.get("title") or "").lower().split())[:80]
        if pid and pid in seen_ids:
            continue
        if title and title in seen_titles:
            continue
        if pid:
            seen_ids.add(pid)
        if title:
            seen_titles.add(title)
        uniq.append(p)

    print(f"  {len(uniq)} פטנטים ייחודיים — מנתח...")

    # Enrich each patent
    for p in uniq:
        p["clusters"]          = _classify_cluster(p)
        p["competitor_owner"]  = _detect_competitor(p)
        p["stardust_overlap"]  = _check_stardust_overlap(p)
        p["tracked_inventor"]  = _detect_tracked_inventor(p)
        p["is_new"]            = False
        p["alert_level"]       = ("immediate" if p["stardust_overlap"] or p["tracked_inventor"]
                                  else "daily" if p["competitor_owner"] else "none")
        p["relevance_score"]   = (9 if p["stardust_overlap"] else
                                  7 if p["tracked_inventor"] else
                                  6 if p["competitor_owner"] else 4)

    # Load previous to detect new patents
    if PREV_FILE.exists():
        try:
            prev_data = json.loads(PREV_FILE.read_text(encoding="utf-8"))
            prev_ids  = {p.get("id") for p in prev_data.get("patents", [])}
            for p in uniq:
                if p["id"] not in prev_ids:
                    p["is_new"] = True
        except Exception:
            pass

    # Save current as prev
    PREV_FILE.write_text(json.dumps({"patents": uniq}, ensure_ascii=False), encoding="utf-8")

    # Build analytics
    gaps     = _detect_gaps(uniq)
    disputes = _detect_disputes(uniq)

    cluster_summary: dict[str, int] = {}
    for p in uniq:
        for cl in p["clusters"]:
            cluster_summary[cl] = cluster_summary.get(cl, 0) + 1

    owner_summary: dict[str, int] = {}
    for p in uniq:
        for a in (p.get("assignees") or []):
            if a:
                owner_summary[a] = owner_summary.get(a, 0) + 1
    top_owners = sorted(owner_summary.items(), key=lambda x: -x[1])[:15]

    competitor_patents = [p for p in uniq if p.get("competitor_owner")]
    overlap_patents    = [p for p in uniq if p.get("stardust_overlap")]
    tracked_patents    = [p for p in uniq if p.get("tracked_inventor")]
    new_patents        = [p for p in uniq if p.get("is_new")]

    output = {
        "generated_at":       now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso":      now.isoformat(),
        "total":              len(uniq),
        "new_count":          len(new_patents),
        "competitor_count":   len(competitor_patents),
        "overlap_count":      len(overlap_patents),
        "patents":            uniq,
        "cluster_summary":    cluster_summary,
        "top_owners":         [{"assignee": a, "count": c} for a, c in top_owners],
        "ip_gaps":            gaps,
        "potential_disputes": disputes,
        "competitor_patents": competitor_patents,
        "stardust_overlap":   overlap_patents,
        "tracked_inventor_patents": tracked_patents,
        "alerts_immediate":   [p for p in uniq if p["alert_level"] == "immediate"],
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {len(uniq)} פטנטים ({len(new_patents)} חדשים, {len(overlap_patents)} חפיפה לStardust) · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
