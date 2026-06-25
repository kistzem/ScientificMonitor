#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
network_analyzer.py — Agent 3: Co-authorship network analysis.
Builds a dynamic collaboration map from all found papers.
Saves: data/network_latest.json
"""

import argparse
import io
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import pytz

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR  = Path(__file__).parent.resolve()
OUTPUT_FILE = SCRIPT_DIR / "data" / "network_latest.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")

sys.path.insert(0, str(SCRIPT_DIR))
from config import TRACKED_ACADEMICS


def _load_all_papers() -> list[dict]:
    papers = []
    for fname in ["papers_latest.json", "academics_latest.json", "competition_latest.json",
                  "preprints_latest.json"]:
        fpath = SCRIPT_DIR / "data" / fname
        if not fpath.exists():
            continue
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            papers.extend(data.get("papers", []))
        except Exception:
            pass
    seen = set()
    uniq = []
    for p in papers:
        if p["id"] not in seen:
            seen.add(p["id"])
            uniq.append(p)
    return uniq


def _normalize_name(name: str) -> str:
    parts = name.strip().split()
    if not parts:
        return name
    # Normalize to "LastName, F." format for dedup
    last = parts[-1].lower()
    first_init = parts[0][0].lower() if parts[0] else ""
    return f"{last}_{first_init}"


def _build_network(papers: list[dict]) -> dict:
    """Build co-authorship graph as adjacency list with weights."""
    edges: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    author_papers: dict[str, list[str]] = defaultdict(list)

    tracked_names = {a["name"].lower() for a in TRACKED_ACADEMICS}

    for paper in papers:
        authors = [a for a in (paper.get("authors") or []) if a and len(a) > 2]
        title   = paper.get("title", "")[:80]
        for auth in authors:
            author_papers[auth].append(title)
        for i, a1 in enumerate(authors):
            for a2 in authors[i+1:]:
                edges[a1][a2] += 1
                edges[a2][a1] += 1

    # Degree centrality (number of unique collaborators)
    nodes = {}
    all_authors = set(edges.keys())
    for author, collabs in edges.items():
        is_tracked = any(t in author.lower() for t in tracked_names) or \
                     any(author.lower() in t for t in tracked_names)
        degree = len(collabs)
        total_collabs = sum(collabs.values())
        nodes[author] = {
            "name":           author,
            "degree":         degree,
            "total_collab_count": total_collabs,
            "is_tracked":     is_tracked,
            "papers_count":   len(set(author_papers.get(author, []))),
            "top_collabs":    sorted(collabs.items(), key=lambda x: -x[1])[:5],
        }

    # Cluster detection: connected components via BFS
    visited  = set()
    clusters = []
    adj      = {k: set(v.keys()) for k, v in edges.items()}

    def bfs(start):
        queue    = [start]
        cluster  = []
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            cluster.append(node)
            queue.extend(adj.get(node, set()) - visited)
        return cluster

    for author in all_authors:
        if author not in visited:
            cluster = bfs(author)
            if len(cluster) >= 2:
                clusters.append(cluster)

    clusters.sort(key=len, reverse=True)

    # Hubs: top 10 by degree among tracked
    tracked_nodes = {k: v for k, v in nodes.items() if v["is_tracked"]}
    hubs = sorted(tracked_nodes.values(), key=lambda x: -x["degree"])[:10]

    # New collaborations: authors who appear in most recent papers with tracked authors
    recent_collabs: list[dict] = []
    for paper in sorted(papers, key=lambda p: p.get("published_date") or "", reverse=True)[:50]:
        authors = paper.get("authors") or []
        has_tracked = any(any(t in a.lower() for t in tracked_names) for a in authors)
        if has_tracked and len(authors) >= 2:
            recent_collabs.append({
                "title":   paper.get("title", "")[:80],
                "date":    paper.get("published_date", ""),
                "authors": authors[:5],
                "source":  paper.get("source", ""),
            })

    # Stardust position in network
    stardust_node = None
    for k, v in nodes.items():
        if "kislev" in k.lower() or "stardust" in k.lower():
            stardust_node = v
            break

    return {
        "nodes":             list(nodes.values())[:200],  # cap for JSON size
        "node_count":        len(nodes),
        "edge_count":        sum(len(v) for v in edges.values()) // 2,
        "cluster_count":     len(clusters),
        "largest_cluster":   clusters[0][:20] if clusters else [],
        "hubs":              hubs,
        "recent_collabs":    recent_collabs[:20],
        "stardust_position": stardust_node,
    }


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[ניתוח רשת] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    all_papers = _load_all_papers()
    print(f"  בונה רשת מ-{len(all_papers)} מאמרים...")

    network = _build_network(all_papers)
    output  = {
        "generated_at":  now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso": now.isoformat(),
        **network,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {output['node_count']} צמתים, {output['edge_count']} קשרים · {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
