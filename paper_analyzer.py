#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paper_analyzer.py — Agent 4: Paper analyzer.
For each paper: generates Hebrew summary, detects contradictions with Stardust,
suggests citations, identifies similar work.
Saves: data/analysis_latest.json
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
OUTPUT_FILE = SCRIPT_DIR / "data" / "analysis_latest.json"
ISRAEL_TZ   = pytz.timezone("Asia/Jerusalem")

sys.path.insert(0, str(SCRIPT_DIR))
from config import CONTRADICTION_TRIGGERS, STARDUST_CLAIMS, SAI_KEYWORDS


def _load_papers() -> list[dict]:
    """Load all papers from field, academic, and competition trackers."""
    papers: list[dict] = []
    for fname in ["papers_latest.json", "academics_latest.json", "competition_latest.json"]:
        fpath = SCRIPT_DIR / "data" / fname
        if not fpath.exists():
            continue
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            papers.extend(data.get("papers", []))
        except Exception:
            pass
    # Deduplicate by id
    seen = set()
    uniq = []
    for p in papers:
        if p["id"] not in seen:
            seen.add(p["id"])
            uniq.append(p)
    return uniq


def _check_contradiction(paper: dict) -> tuple[bool, str]:
    """Check if paper potentially contradicts Stardust's core claims."""
    text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
    triggered = [t for t in CONTRADICTION_TRIGGERS if t.lower() in text]
    if not triggered:
        return False, ""

    details_he = "מאמר זה עשוי לסתור טענות מפתח של Stardust:\n"
    for t in triggered[:3]:
        details_he += f"• ממצא: '{t}'\n"
    details_he += "נדרשת עיון נוסף לאימות ההשפעה על פרופיל הבטיחות של Stardust."
    return True, details_he


def _check_stardust_overlap(paper: dict) -> str:
    """Check overlap with Stardust research areas."""
    text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
    overlaps = []
    if any(k.lower() in text for k in ["silica", "sio2", "silicon dioxide"]):
        overlaps.append("חומרי סיליקה")
    if any(k.lower() in text for k in ["caco3", "calcium carbonate", "calcite"]):
        overlaps.append("סידן קרבונט")
    if any(k.lower() in text for k in ["heterogeneous", "surface uptake", "surface chemistry"]):
        overlaps.append("כימיה הטרוגנית")
    if any(k.lower() in text for k in ["ozone", "ozone depletion", "ozone loss"]):
        overlaps.append("כימיית אוזון")
    return ", ".join(overlaps)


def _generate_citation_suggestion(paper: dict) -> str:
    """Generate a suggested citation context for Stardust's next paper."""
    title   = paper.get("title", "")
    authors = paper.get("authors", [])
    year    = (paper.get("published_date") or "")[:4]
    author1 = authors[0].split()[-1] if authors else "et al."
    et_al   = " et al." if len(authors) > 1 else ""

    text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()

    if any(k in text for k in ["silica", "sio2"]):
        return f"לאישוש תכונות הסיליקה: ({author1}{et_al}, {year}): \"{title[:60]}...\""
    if any(k in text for k in ["heterogeneous", "uptake coefficient"]):
        return f"לנתוני קצב קליטה הטרוגנית: ({author1}{et_al}, {year}): \"{title[:60]}...\""
    if any(k in text for k in ["ozone", "stratospheric chemistry"]):
        return f"לרקע כימיית האוזון: ({author1}{et_al}, {year}): \"{title[:60]}...\""
    if any(k in text for k in ["aerosol optical", "radiative forcing"]):
        return f"להשפעה רדיאטיבית: ({author1}{et_al}, {year}): \"{title[:60]}...\""
    return f"מקור כללי רלוונטי: ({author1}{et_al}, {year}): \"{title[:60]}...\""


def _generate_hebrew_summary(paper: dict) -> str:
    """Generate a structured Hebrew summary based on paper data."""
    title   = paper.get("title", "")
    authors = paper.get("authors", [])
    year    = (paper.get("published_date") or "")[:4]
    source  = paper.get("source", "")
    abstract = paper.get("abstract", "")
    overlap = _check_stardust_overlap(paper)

    source_map = {
        "arxiv": "arXiv (פרה-פרינט)",
        "pubmed": "PubMed",
        "semantic_scholar": "Semantic Scholar",
        "patent": "מסד נתוני פטנטים",
    }
    source_he = source_map.get(source, source)
    authors_str = ", ".join(authors[:3]) + (" ועוד" if len(authors) > 3 else "")

    lines = [f"📄 **{title}**"]
    lines.append(f"✍️ מחברים: {authors_str}")
    lines.append(f"📅 שנה: {year} | מקור: {source_he}")

    if abstract:
        first_sent = re.split(r'[.!?]', abstract)[0].strip()
        if first_sent:
            lines.append(f"📝 עיקרון: {first_sent[:200]}")

    if overlap:
        lines.append(f"🔗 חפיפה לStardust: {overlap}")
    else:
        lines.append("🔗 חפיפה לStardust: חפיפה כללית לתחום SAI")

    keywords = paper.get("keywords_matched", [])
    if keywords:
        lines.append(f"🔑 מילות מפתח: {', '.join(keywords[:3])}")

    return "\n".join(lines)


def _find_similar_work_note(paper: dict, all_papers: list[dict]) -> str:
    """Find other papers with similar content."""
    text_main = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
    main_words = set(w for w in re.findall(r'\b[a-z]{5,}\b', text_main) if w not in
                     {"which", "where", "their", "these", "there", "about", "using", "study"})

    similar = []
    for other in all_papers:
        if other["id"] == paper["id"]:
            continue
        text_other = (other.get("title", "") + " " + other.get("abstract", "")).lower()
        other_words = set(re.findall(r'\b[a-z]{5,}\b', text_other))
        overlap = len(main_words & other_words)
        if overlap > 8:
            author1 = other["authors"][0].split()[-1] if other.get("authors") else "?"
            similar.append(f"{author1} ({(other.get('published_date') or '')[:4]}): {other['title'][:60]}")
        if len(similar) >= 2:
            break
    if similar:
        return "עבודות דומות:\n" + "\n".join(f"• {s}" for s in similar)
    return ""


def analyze_paper(paper: dict, all_papers: list[dict]) -> dict:
    """Analyze a single paper. Returns analysis dict."""
    contradicts, contradiction_details = _check_contradiction(paper)
    return {
        "paper_id":              paper["id"],
        "summary_he":            _generate_hebrew_summary(paper),
        "contradicts_stardust":  contradicts,
        "contradiction_details": contradiction_details,
        "citation_suggestion":   _generate_citation_suggestion(paper),
        "similar_work":          _find_similar_work_note(paper, all_papers),
        "stardust_overlap":      _check_stardust_overlap(paper),
    }


def run() -> dict:
    now = datetime.now(ISRAEL_TZ)
    print(f"[ניתוח מאמרים] {now.strftime('%d/%m/%Y %H:%M')}")
    OUTPUT_FILE.parent.mkdir(exist_ok=True)

    all_papers = _load_papers()
    print(f"  מנתח {len(all_papers)} מאמרים...")

    analyses = {}
    contradictions = 0
    for paper in all_papers:
        result = analyze_paper(paper, all_papers)
        analyses[paper["id"]] = result
        if result["contradicts_stardust"]:
            contradictions += 1
            paper["contradicts_stardust"]  = True
            paper["contradiction_details"] = result["contradiction_details"]

    output = {
        "generated_at":    now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso":   now.isoformat(),
        "total_analyzed":  len(analyses),
        "contradictions":  contradictions,
        "analyses":        analyses,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → {len(analyses)} נותחו, {contradictions} סתירות · נשמר: {OUTPUT_FILE.name}")
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
