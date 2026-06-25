#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
controversy_detector.py — Agent 4: Controversy detector.
Finds disagreements between papers in the SAI field.
Saves: data/controversies_latest.json
"""

import argparse
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pytz

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR  = Path(__file__).parent.resolve()
OUTPUT_FILE = SCRIPT_DIR / "data" / "controversies_latest.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")

sys.path.insert(0, str(SCRIPT_DIR))
from config import STARDUST_CLAIMS

# Phrases indicating disagreement with prior work
DISAGREEMENT_PHRASES = [
    "contrary to", "in contrast to", "contradicts", "challenges the view",
    "we find no evidence", "we dispute", "our results do not support",
    "does not agree with", "inconsistent with previous", "differs from",
    "at odds with", "in disagreement with", "challenges previous findings",
    "our data suggest the opposite", "we question", "we challenge",
    "revisiting the assumption", "our results contradict",
]

# Claim pairs that might conflict
CLAIM_PAIRS = [
    ("ozone increase", "ozone decrease"),
    ("ozone depletion increases", "ozone depletion decreases"),
    ("silica safe", "silica harmful"),
    ("CaCO3 neutral", "CaCO3 ozone"),
    ("aerosol warms", "aerosol cools"),
    ("precipitation increases", "precipitation decreases"),
    ("monsoon strengthens", "monsoon weakens"),
    ("termination shock severe", "termination shock manageable"),
    ("SAI reduces", "SAI increases"),
    ("particles grow", "particles shrink"),
]


def _load_all_papers() -> list[dict]:
    papers = []
    for fname in ["papers_latest.json", "academics_latest.json",
                  "competition_latest.json", "preprints_latest.json"]:
        fpath = SCRIPT_DIR / "data" / fname
        if not fpath.exists():
            continue
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            papers.extend(data.get("papers", []))
        except Exception:
            pass
    seen = set()
    return [p for p in papers if not (seen.add(p["id"]) if p["id"] not in seen else True)]


def _has_disagreement_phrase(abstract: str) -> list[str]:
    abstract_lower = abstract.lower()
    return [ph for ph in DISAGREEMENT_PHRASES if ph in abstract_lower]


def _detect_conflicting_claims(papers: list[dict]) -> list[dict]:
    """Find paper pairs that make opposing claims."""
    controversies = []
    n = len(papers)

    # Simple approach: for each paper with disagreement phrase, find what it disagrees with
    for i, paper in enumerate(papers):
        abstract = paper.get("abstract") or ""
        title    = paper.get("title") or ""
        phrases  = _has_disagreement_phrase(abstract)
        if not phrases:
            continue

        # Check against CLAIM_PAIRS for explicit contradictions
        text = (title + " " + abstract).lower()
        conflicting_with = []
        for pos, neg in CLAIM_PAIRS:
            if pos.lower() in text and neg.lower() not in text:
                # This paper makes the positive claim
                # Find papers making the negative claim
                for j, other in enumerate(papers):
                    if i == j:
                        continue
                    other_text = ((other.get("title") or "") + " " + (other.get("abstract") or "")).lower()
                    if neg.lower() in other_text and pos.lower() not in other_text:
                        conflicting_with.append({
                            "opposing_paper_id":    other["id"],
                            "opposing_paper_title": other.get("title", "")[:80],
                            "opposing_authors":     (other.get("authors") or [])[:3],
                            "claim_a":              pos,
                            "claim_b":              neg,
                        })
                        break

        if phrases or conflicting_with:
            stardust_impact = "low"
            for claim_key, keywords in STARDUST_CLAIMS.items():
                if any(kw.lower() in text for kw in keywords):
                    stardust_impact = "high"
                    break

            controversies.append({
                "paper_id":          paper["id"],
                "title":             paper.get("title", "")[:100],
                "authors":           (paper.get("authors") or [])[:3],
                "published_date":    paper.get("published_date", ""),
                "url":               paper.get("url", ""),
                "disagreement_phrases": phrases[:3],
                "conflicting_with":  conflicting_with[:3],
                "stardust_impact":   stardust_impact,
                "summary_he":        _summarize_controversy_he(paper, phrases, conflicting_with),
            })

    return controversies


def _summarize_controversy_he(paper: dict, phrases: list, conflicts: list) -> str:
    authors = (paper.get("authors") or [])
    auth1   = authors[0] if authors else "מחבר לא ידוע"
    title   = paper.get("title") or ""
    lines   = [f"📄 {title[:80]}"]
    lines.append(f"✍️ {auth1}" + (" ועוד" if len(authors) > 1 else ""))
    if phrases:
        lines.append(f"⚔️ ביטויי מחלוקת: {', '.join(phrases[:2])}")
    if conflicts:
        c = conflicts[0]
        lines.append(f"🔴 סותר: '{c['claim_a']}' מול '{c['claim_b']}'")
        lines.append(f"   בניגוד ל: {c['opposing_paper_title'][:60]}")
    return "\n".join(lines)


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[Controversy Detector] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    all_papers    = _load_all_papers()
    controversies = _detect_conflicting_claims(all_papers)

    high_impact   = [c for c in controversies if c["stardust_impact"] == "high"]
    print(f"  {len(controversies)} מחלוקות ({len(high_impact)} השפעה גבוהה על Stardust)")

    output = {
        "generated_at":   now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso":  now.isoformat(),
        "total":          len(controversies),
        "high_impact":    len(high_impact),
        "controversies":  controversies,
        "high_impact_list": high_impact,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
