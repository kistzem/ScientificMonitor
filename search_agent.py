#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
search_agent.py — SAI paper search + dashboard generator.
Sources: Semantic Scholar (topics), arXiv (authors + topics).
Saves: data/search_results.json  +  dashboard.html
"""

import io, json, re, sys, time, xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus
import requests, pytz

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_FILE  = SCRIPT_DIR / "data" / "search_results.json"
HTML_FILE  = SCRIPT_DIR / "dashboard.html"
ISRAEL_TZ  = pytz.timezone("Asia/Jerusalem")
PORT       = 5759

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "ScientificMonitor/1.0 (t.kislev@stardust-initiative.com)"})

# ── Tracked researchers (🔴) — last-name for arXiv au: search ────────────────
TRACKED_RESEARCHERS = [
    ("Tzemah Kislev",       "Kislev"),
    ("Vicki Grassian",      "Grassian"),
    ("Dan Cziczo",          "Cziczo"),
    ("Alan Robock",         "Robock"),
    ("Ben Kravitz",         "Kravitz"),
    ("Frank Keutsch",       "Keutsch"),
    ("James Haywood",       "Haywood"),
    ("Simone Tilmes",       "Tilmes"),
    ("Daniele Visioni",     "Visioni"),
    ("Michael Diamond",     "Diamond"),
    ("Kate Ricke",          "Ricke"),
    ("Peter Irvine",        "Irvine"),
    ("David Keith",         "Keith"),
    ("John Dykema",         "Dykema"),
    ("Debra Weisenstein",   "Weisenstein"),
    ("Douglas MacMartin",   "MacMartin"),
    ("Joshua Schwarz",      "Schwarz"),
    ("Shuchi Talati",       "Talati"),
]

# Batched by 5 for arXiv au: queries
_RESEARCHER_BATCHES = [
    TRACKED_RESEARCHERS[i:i+5] for i in range(0, len(TRACKED_RESEARCHERS), 5)
]

# ── Competitor companies (🔴) ─────────────────────────────────────────────────
COMPETITOR_COMPANIES = [
    "Make Sunsets", "Reflective", "Parasol", "SilverLining",
    "Silver Lining", "SCoPEx",
]

# ── Topic search queries (🟡) ─────────────────────────────────────────────────
TOPIC_QUERIES_S2 = [
    "stratospheric aerosol injection SAI climate",
    "heterogeneous uptake silica aerosol stratosphere",
    "solar radiation management SRM geoengineering",
    "ozone PSC polar stratospheric aerosol",
]
TOPIC_QUERIES_ARXIV = [
    "stratospheric aerosol injection",
    "heterogeneous uptake silica",
    "atmospheric chemistry aerosol ozone stratosphere",
    "solar radiation management",
]

# ── Scoring constants ─────────────────────────────────────────────────────────
CORE_TERMS = [
    ("stratospheric aerosol injection", 3), ("SAI", 3), ("silica aerosol", 3),
    ("heterogeneous uptake", 3), ("solar radiation management", 2), ("SRM", 2),
    ("geoengineering aerosol", 2), ("aerosol injection", 2),
]
RELATED_TERMS = [
    ("ozone depletion", 1), ("polar stratospheric", 1), ("PSC", 1),
    ("stratospheric aerosol", 1), ("radiative forcing", 1),
    ("aerosol chemistry", 1), ("ozone chemistry", 1), ("CaCO3", 1),
]
TOP_JOURNALS = {
    "Nature", "Science", "PNAS", "Environmental Science & Technology",
    "Atmospheric Chemistry and Physics", "ACP", "Geophysical Research Letters",
    "GRL", "Journal of Geophysical Research", "JGR", "Climatic Change",
    "Nature Climate Change", "Aerosol Science and Technology",
    "Journal of Aerosol Science", "Atmospheric Environment",
}
STARDUST_TERMS = [
    "silica", "SiO2", "heterogeneous uptake", "non-sulfate aerosol",
    "engineered particle", "stratospheric particle",
]

_RESULT_PHRASES = [
    "we show", "we find", "we demonstrate", "results show", "results indicate",
    "we report", "we observe", "model results", "simulations show",
    "we conclude", "experiments show", "data suggest",
]
_TOPIC_MAP = [
    ("stratospheric aerosol injection",   "הזרקת אירוסולים סטרטוספריים"),
    ("solar radiation management",        "ניהול קרינה סולארית"),
    ("heterogeneous uptake",              "ספיחה הטרוגנית"),
    ("silica",                            "חלקיקי סיליקה"),
    ("polar stratospheric",               "ענני סטרטוספרה קוטביים (PSC)"),
    ("ozone depletion",                   "דלדול האוזון"),
    ("ozone chemistry",                   "כימיית האוזון"),
    ("aerosol injection",                 "הזרקת אירוסולים"),
    ("sulfate aerosol",                   "אירוסולי סולפט"),
    ("geoengineering",                    "הנדסת אקלים"),
    ("aerosol",                           "אירוסולים אטמוספריים"),
    ("ozone",                             "שכבת האוזון"),
]
_METHOD_MAP = [
    (("model", "gcm", "simulation"),         "מודלים"),
    (("laborator", "chamber", "experiment"), "ניסויי מעבדה"),
    (("lidar", "satellite", "remote sens"),  "תצפיות מרחוק"),
    (("observ", "measurement", "field"),     "מדידות ותצפיות"),
    (("review",),                            "סקירת ספרות"),
]


# ── Retry wrapper ─────────────────────────────────────────────────────────────
def _get(url, params, timeout=20, retries=3, base_wait=8) -> requests.Response | None:
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                wait = base_wait * (2 ** attempt)
                print(f"    ⏳ rate-limit, wait {wait}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.Timeout:
            print(f"    ⚠️ timeout (attempt {attempt+1})")
            time.sleep(4)
        except Exception as e:
            print(f"    ❌ {e}")
            return None
    return None


# ── Semantic Scholar ──────────────────────────────────────────────────────────
def _s2_search(query: str, days: int = 90) -> list[dict]:
    cutoff = (datetime.now(ISRAEL_TZ) - timedelta(days=days)).strftime("%Y-%m-%d")
    r = _get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={
            "query":  query,
            "fields": "paperId,title,authors,abstract,publicationDate,year,"
                      "externalIds,openAccessPdf,publicationVenue,citationCount",
            "limit":  25,
        },
    )
    if not r:
        return []
    out = []
    for p in r.json().get("data", []):
        date = (p.get("publicationDate") or f"{p.get('year','')}-01-01")[:10]
        if date and date < cutoff:
            continue
        ext   = p.get("externalIds") or {}
        doi   = ext.get("DOI", "")
        arxiv = ext.get("ArXiv", "")
        url   = (f"https://arxiv.org/abs/{arxiv}" if arxiv
                 else f"https://doi.org/{doi}" if doi
                 else f"https://www.semanticscholar.org/paper/{p.get('paperId','')}")
        oap   = p.get("openAccessPdf") or {}
        venue = (p.get("publicationVenue") or {}).get("name", "")
        out.append({
            "id":        f"s2:{p.get('paperId','')}",
            "title":     p.get("title") or "",
            "authors":   [a["name"] for a in p.get("authors", [])][:6],
            "abstract":  (p.get("abstract") or "")[:800],
            "date":      date,
            "journal":   venue,
            "url":       url,
            "pdf":       oap.get("url", ""),
            "citations": p.get("citationCount", 0) or 0,
            "source":    "Semantic Scholar",
            "query":     query,
        })
    return out


# ── arXiv ─────────────────────────────────────────────────────────────────────
def _arxiv_search(query: str, days: int = 90, max_results: int = 15) -> list[dict]:
    cutoff = datetime.now(ISRAEL_TZ) - timedelta(days=days)
    r = _get(
        "https://export.arxiv.org/api/query",
        params={
            "search_query": query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        },
        base_wait=5,
    )
    if not r:
        return []
    ns = "http://www.w3.org/2005/Atom"
    try:
        root = ET.fromstring(r.text)
    except Exception:
        return []
    out = []
    for entry in root.findall(f"{{{ns}}}entry"):
        raw = (entry.findtext(f"{{{ns}}}published") or "")[:10]
        try:
            if datetime.fromisoformat(raw).replace(tzinfo=ISRAEL_TZ) < cutoff:
                continue
        except Exception:
            pass
        arxiv_id = (entry.findtext(f"{{{ns}}}id") or "").split("/abs/")[-1]
        title    = re.sub(r"\s+", " ", entry.findtext(f"{{{ns}}}title") or "").strip()
        abstract = re.sub(r"\s+", " ", entry.findtext(f"{{{ns}}}summary") or "")[:800]
        authors  = [a.findtext(f"{{{ns}}}name") or ""
                    for a in entry.findall(f"{{{ns}}}author")][:6]
        pdf_url  = next((l.get("href","") for l in entry.findall(f"{{{ns}}}link")
                         if l.get("title") == "pdf"), "")
        out.append({
            "id":        f"arxiv:{arxiv_id}",
            "title":     title,
            "authors":   authors,
            "abstract":  abstract,
            "date":      raw,
            "journal":   "arXiv",
            "url":       f"https://arxiv.org/abs/{arxiv_id}",
            "pdf":       pdf_url or f"https://arxiv.org/pdf/{arxiv_id}",
            "citations": 0,
            "source":    "arXiv",
            "query":     query,
        })
    return out


# ── Classification ────────────────────────────────────────────────────────────
def _classify(paper: dict) -> dict:
    author_str = " ".join(paper.get("authors", [])).lower()
    all_text   = " ".join([paper.get("title",""), paper.get("abstract",""),
                            *paper.get("authors",[])]).lower()
    for full_name, last in TRACKED_RESEARCHERS:
        if last.lower() in author_str:
            return {"status": "researcher", "matched": full_name, "priority": "red"}
    for company in COMPETITOR_COMPANIES:
        if company.lower() in all_text:
            return {"status": "competition", "matched": company, "priority": "red"}
    return {"status": "general", "matched": "", "priority": "yellow"}


def _score(paper: dict, cls: dict) -> int:
    text  = ((paper.get("title") or "") + " " + (paper.get("abstract") or "")).lower()
    total = 0
    for term, w in CORE_TERMS:
        if term.lower() in text:
            total += w
    for term, w in RELATED_TERMS:
        if term.lower() in text:
            total += w
    if any(j.lower() in (paper.get("journal") or "").lower() for j in TOP_JOURNALS):
        total += 1
    if paper.get("citations", 0) >= 50:
        total += 1
    if cls.get("status") == "researcher":
        total += 4
    elif cls.get("status") == "competition":
        total += 3
    return max(1, min(10, round(total * 10 / 14)))


def _stardust(paper: dict) -> bool:
    text = ((paper.get("title") or "") + " " + (paper.get("abstract") or "")).lower()
    return any(t.lower() in text for t in STARDUST_TERMS)


def _hebrew_summary(paper: dict, cls: dict) -> str:
    abstract = (paper.get("abstract") or "")
    text     = (paper.get("title") or "").lower() + " " + abstract.lower()

    topic  = next((he for en, he in _TOPIC_MAP if en in text), "אירוסולים אטמוספריים")
    method = next((he for kws, he in _METHOD_MAP if any(k in text for k in kws)), "")
    method_str = f" תוך שימוש ב{method}" if method else ""

    finding = ""
    for phrase in _RESULT_PHRASES:
        idx = abstract.lower().find(phrase)
        if idx >= 0:
            snip = abstract[idx:idx+220]
            end  = snip.find(". ")
            c    = (snip[:end] if end > 0 else snip).strip()
            if len(c) > 30:
                finding = c; break

    if cls.get("status") == "researcher":
        prefix = f"🔴 מאמר חדש מאת {cls['matched']} — "
    elif cls.get("status") == "competition":
        prefix = f"🔴 {cls['matched']} — "
    else:
        prefix = ""

    s1 = f"{prefix}מחקר זה עוסק ב{topic}{method_str}."
    s2 = f" מהממצאים: \"{finding[:180]}\"" if finding else \
         (f" תקציר: \"{abstract.split('. ')[0][:160]}\"" if abstract else "")
    sd = " ⚠️ רלוונטי ישירות לStardust." if _stardust(paper) else ""
    return f"{s1}{s2}.{sd}"


# ── Dedup ─────────────────────────────────────────────────────────────────────
def _dedup(papers: list[dict]) -> list[dict]:
    seen_ids, seen_titles, out = set(), set(), []
    for p in papers:
        pid   = p["id"]
        tnorm = re.sub(r"[^a-z0-9]", "", (p.get("title") or "").lower())[:60]
        if pid in seen_ids or (tnorm and tnorm in seen_titles):
            continue
        seen_ids.add(pid); seen_titles.add(tnorm) if tnorm else None
        out.append(p)
    return out


# ── HTML ──────────────────────────────────────────────────────────────────────
def _html(papers: list[dict], generated_at: str) -> None:
    clean = [{k: v for k, v in p.items() if k != "_cls"} for p in papers]
    pj    = json.dumps(clean, ensure_ascii=False)

    HTML_FILE.write_text(f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>ScientificMonitor — SAI Intelligence</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',Arial,sans-serif;font-size:13px;background:#08111e;color:#c8d8e8;direction:rtl;min-height:100vh}}
a{{text-decoration:none}}
#hdr{{background:linear-gradient(135deg,#0a1a2e,#0f2540);border-bottom:2px solid #1a3555;padding:10px 20px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;flex-wrap:wrap;gap:8px}}
#hdr h1{{font-size:15px;font-weight:700;color:#5bc8fa;white-space:nowrap}}
.hdr-r{{display:flex;align-items:center;gap:10px;font-size:11px;color:#4a6a8a;flex-wrap:wrap}}
#bar{{background:#0b1c2e;border-bottom:1px solid #162840;padding:8px 20px;display:flex;gap:18px;align-items:center;flex-wrap:wrap;font-size:11px}}
.kv{{display:flex;align-items:baseline;gap:3px}} .kpi{{font-weight:700;font-size:17px}} .kpi-lbl{{color:#4a6a8a}}
.sep{{width:1px;height:20px;background:#162840}}
.controls{{display:flex;gap:8px;align-items:center;margin-right:auto;flex-wrap:wrap}}
input,select{{padding:5px 10px;border:1px solid #1a3555;border-radius:5px;background:#0f2030;color:#c8d8e8;font-size:12px;font-family:inherit}}
input:focus,select:focus{{outline:none;border-color:#5bc8fa}} input{{width:210px}}
#banner{{display:none;background:#4a0808;border-bottom:2px solid #e74c3c;padding:7px 20px;font-size:12px;color:#ffcccc}}
#banner.show{{display:block}}
#tabs{{display:flex;background:#0c1c2e;border-bottom:1px solid #162840;overflow-x:auto}}
.tab{{padding:8px 16px;border:none;background:none;color:#4a6a8a;font-size:12px;font-weight:700;cursor:pointer;border-bottom:3px solid transparent;font-family:inherit;white-space:nowrap}}
.tab.active{{color:#5bc8fa;border-bottom-color:#5bc8fa;background:#0a1628}}
.tab:hover{{color:#c8d8e8;background:#0f2030}}
.tbdg{{background:#e74c3c;color:#fff;border-radius:8px;padding:1px 5px;font-size:9px;margin-right:3px;vertical-align:top}}
#main{{padding:12px 20px;max-width:1300px;margin:0 auto}}
.card{{background:#fff;border-radius:8px;margin-bottom:9px;padding:13px 16px;border-right:4px solid #dee2e6;box-shadow:0 1px 4px rgba(0,0,0,.06);color:#1e2e40;transition:box-shadow .15s}}
.card:hover{{box-shadow:0 3px 14px rgba(0,0,0,.14)}}
.card.researcher{{border-right-color:#e74c3c;background:#fff8f8}}
.card.competition{{border-right-color:#e67e22;background:#fffbf5}}
.card.stardust{{border-right-color:#9b59b6}}
.card-top{{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}}
.card-title{{font-size:13px;font-weight:700;color:#0f2540;line-height:1.35;flex:1}}
.card-title:hover{{color:#3498db}}
.score{{flex-shrink:0;width:27px;height:27px;border-radius:50%;font-size:11px;font-weight:700;color:#fff;display:flex;align-items:center;justify-content:center}}
.card-meta{{font-size:11px;color:#6b8099;margin-top:5px;display:flex;flex-wrap:wrap;gap:7px;align-items:center}}
.chip{{display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:700;white-space:nowrap}}
.chip-red{{background:#fee2e2;color:#991b1b}} .chip-orange{{background:#fef3c7;color:#92400e}}
.chip-blue{{background:#dbeafe;color:#1d4ed8}} .chip-green{{background:#dcfce7;color:#166534}}
.chip-gray{{background:#f1f5f9;color:#475569}} .chip-purple{{background:#f3e8ff;color:#6b21a8}}
.card-summary{{font-size:12px;color:#374151;margin-top:8px;line-height:1.65;background:#f8fafc;padding:8px 11px;border-radius:5px;border-right:3px solid #5bc8fa}}
.card-summary.alert{{border-right-color:#e74c3c;background:#fff8f8}}
.card-btns{{margin-top:8px;display:flex;gap:6px}}
.btn{{padding:4px 12px;border:none;border-radius:5px;font-size:11px;font-weight:700;cursor:pointer;font-family:inherit}}
.btn-blue{{background:#3498db;color:#fff}} .btn-blue:hover{{background:#2980b9}}
.btn-green{{background:#27ae60;color:#fff}} .btn-green:hover{{background:#219a52}}
.btn-refresh{{background:#5bc8fa;color:#0a1628;font-size:12px;padding:6px 14px}}
.btn-refresh:hover{{background:#4ab8ea}}
.empty{{text-align:center;color:#4a6a8a;padding:40px;font-size:14px}}
</style>
</head>
<body>
<div id="hdr">
  <h1>🔬 ScientificMonitor — SAI/SRM Intelligence</h1>
  <div class="hdr-r">
    <span id="ts">{generated_at}</span>
    <button class="btn btn-refresh" onclick="doRefresh()" id="refresh-btn">🔄 עדכן עכשיו</button>
    <span id="st" style="font-size:10px;max-width:200px"></span>
  </div>
</div>
<div id="banner"></div>
<div id="bar">
  <div class="kv"><span class="kpi" id="cnt-all" style="color:#5bc8fa">—</span><span class="kpi-lbl"> מאמרים</span></div>
  <div class="sep"></div>
  <div class="kv"><span class="kpi" id="cnt-alert" style="color:#e74c3c">—</span><span class="kpi-lbl"> 🔴 התראות</span></div>
  <div class="sep"></div>
  <div class="kv"><span class="kpi" id="cnt-week" style="color:#f39c12">—</span><span class="kpi-lbl"> השבוע</span></div>
  <div class="sep"></div>
  <div class="kv"><span class="kpi" id="cnt-stardust" style="color:#9b59b6">—</span><span class="kpi-lbl"> Stardust</span></div>
  <div class="controls">
    <input id="search" placeholder="חיפוש כותרת / מחבר..." oninput="render()">
    <select id="filter-score" onchange="render()">
      <option value="0">כל הציונים</option><option value="7">ציון 7+</option><option value="8">ציון 8+</option>
    </select>
  </div>
</div>
<div id="tabs">
  <button class="tab active" onclick="sw('all',this)">📋 הכל<span id="bdg-all" class="tbdg" style="display:none"></span></button>
  <button class="tab" onclick="sw('researcher',this)">🔴 חוקרים<span id="bdg-res" class="tbdg" style="display:none"></span></button>
  <button class="tab" onclick="sw('competition',this)">🟠 תחרות<span id="bdg-comp" class="tbdg" style="display:none"></span></button>
  <button class="tab" onclick="sw('general',this)">🟡 כללי</button>
  <button class="tab" onclick="sw('stardust',this)">⚠️ Stardust<span id="bdg-sd" class="tbdg" style="background:#9b59b6;display:none"></span></button>
</div>
<div id="main"><div id="cards"></div></div>
<script>
const ALL={pj},PORT={PORT};
let _f='all';
const $=id=>document.getElementById(id),sc=s=>s>=8?'#27ae60':s>=5?'#f39c12':'#95a5a6';
function init(){{
  const wk=new Date();wk.setDate(wk.getDate()-7);const wkStr=wk.toISOString().slice(0,10);
  const alerts=ALL.filter(p=>p.priority==='red');
  const sd=ALL.filter(p=>p.stardust);
  const rn=ALL.filter(p=>p.status==='researcher').length;
  const cn=ALL.filter(p=>p.status==='competition').length;
  $('cnt-all').textContent=ALL.length;
  $('cnt-alert').textContent=alerts.length;
  $('cnt-week').textContent=ALL.filter(p=>p.date>=wkStr).length;
  $('cnt-stardust').textContent=sd.length;
  if(rn){{$('bdg-res').textContent=rn;$('bdg-res').style.display='';}}
  if(cn){{$('bdg-comp').textContent=cn;$('bdg-comp').style.display='';}}
  if(sd.length){{$('bdg-sd').textContent=sd.length;$('bdg-sd').style.display='';}}
  $('bdg-all').textContent=ALL.length;$('bdg-all').style.display='';
  if(alerts.length){{
    const ban=$('banner');
    ban.innerHTML='🔴 <b>התראות מיידיות:</b> '+alerts.slice(0,4).map(p=>
      `<a href="${{p.url}}" target="_blank" style="color:#ffa0a0;font-weight:700">${{p.matched||''}}</a>: ${{(p.title||'').slice(0,55)}}...`
    ).join(' | ');
    ban.classList.add('show');
  }}
  render();
}}
function sw(val,btn){{
  _f=val;
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  if(btn)btn.classList.add('active');
  render();
}}
function render(){{
  const q=($('search').value||'').toLowerCase();
  const ms=parseInt($('filter-score').value||0);
  let pp=ALL.filter(p=>{{
    if(_f==='stardust'&&!p.stardust)return false;
    else if(_f!=='all'&&_f!=='stardust'&&p.status!==_f)return false;
    if(p.score<ms)return false;
    if(!q)return true;
    return((p.title||'')+(p.authors||[]).join(' ')+(p.abstract||'')).toLowerCase().includes(q);
  }});
  pp.sort((a,b)=>{{
    if(a.priority==='red'&&b.priority!=='red')return -1;
    if(b.priority==='red'&&a.priority!=='red')return 1;
    if(b.score!==a.score)return b.score-a.score;
    return(b.date||'')>(a.date||'')?1:-1;
  }});
  if(!pp.length){{$('cards').innerHTML='<div class="empty">אין תוצאות</div>';return;}}
  $('cards').innerHTML=pp.map(p=>{{
    const cc=p.status==='researcher'?'card researcher':p.status==='competition'?'card competition':p.stardust?'card stardust':'card';
    const sch=p.status==='researcher'?`<span class="chip chip-red">🔴 ${{p.matched}}</span>`:
              p.status==='competition'?`<span class="chip chip-orange">🟠 ${{p.matched}}</span>`:
              `<span class="chip chip-gray">🟡 כללי</span>`;
    const jch=p.journal&&p.journal!=='arXiv'?`<span class="chip chip-blue">📰 ${{p.journal.slice(0,28)}}</span>`:
              `<span class="chip chip-green">📄 arXiv</span>`;
    const stch=p.stardust?`<span class="chip chip-purple">⚠️ Stardust</span>`:'';
    const auth=(p.authors||[]).slice(0,4).join(', ')+(p.authors&&p.authors.length>4?` +${{p.authors.length-4}}`:'');
    const pdfb=p.pdf?`<a href="${{p.pdf}}" target="_blank" class="btn btn-green">PDF</a>`:'';
    const smc=p.priority==='red'?'card-summary alert':'card-summary';
    return`<div class="${{cc}}">
      <div class="card-top">
        <a class="card-title" href="${{p.url}}" target="_blank">${{p.title||'ללא כותרת'}}</a>
        <div class="score" style="background:${{sc(p.score)}}" title="ציון ${{p.score}}/10">${{p.score}}</div>
      </div>
      <div class="card-meta">${{sch}} ${{jch}} ${{stch}}
        <span class="chip chip-gray">📅 ${{p.date||'?'}}</span>
        ${{p.citations>0?`<span class="chip chip-gray">🔗 ${{p.citations}} ציטוטים</span>`:''}}
        <span style="color:#6b8099">${{auth}}</span>
      </div>
      <div class="${{smc}}">${{p.summary_he||''}}</div>
      <div class="card-btns">
        <a href="${{p.url}}" target="_blank" class="btn btn-blue">קרא מאמר</a>
        ${{pdfb}}
      </div>
    </div>`;
  }}).join('');
}}
async function doRefresh(){{
  const btn=$('refresh-btn'),st=$('st');
  btn.disabled=true;btn.textContent='⏳ מריץ...';st.textContent='';
  try{{
    const r=await fetch(`http://localhost:${{PORT}}/refresh`,{{method:'POST'}});
    const d=await r.json();
    if(d.error==='כבר רץ'){{st.textContent='⏳ כבר רץ...';}}
    else if(d.status==='started'){{
      st.textContent='⏳ מחפש...';
      const iv=setInterval(async()=>{{
        try{{
          const s=await(await fetch(`http://localhost:${{PORT}}/status`)).json();
          if(!s.running){{clearInterval(iv);setTimeout(()=>location.reload(),1000);}}
          else st.textContent='⏳'+((s.output||[]).slice(-1)[0]||'');
        }}catch{{}}
      }},2000);
    }}
  }}catch{{st.textContent='❌ שגיאת חיבור';btn.disabled=false;btn.textContent='🔄 עדכן עכשיו';}}
}}
init();
</script>
</body>
</html>""".replace("{papers_json_placeholder}", pj).replace("{PORT}", str(PORT))
              .replace("{generated_at}", generated_at), encoding="utf-8")
    print(f"  → dashboard.html ({HTML_FILE.stat().st_size//1024} KB)")


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> None:
    now = datetime.now(ISRAEL_TZ)
    print(f"\n{'='*55}")
    print(f"[ScientificMonitor] {now.strftime('%d/%m/%Y %H:%M')}")
    SCRIPT_DIR.joinpath("data").mkdir(exist_ok=True)

    all_papers: list[dict] = []

    # ── 1. Researcher batches via arXiv ──────────────────────────────────────
    print("\n── חוקרים (arXiv) ──")
    for batch in _RESEARCHER_BATCHES:
        names_query = " OR ".join(f"au:{last}" for _, last in batch)
        label = ", ".join(full for full, _ in batch)
        print(f"  🔍 {label[:60]}")
        res = _arxiv_search(names_query, days=60, max_results=20)
        print(f"     arXiv: {len(res)}")
        all_papers.extend(res)
        time.sleep(2.5)

    # ── 2. Topic searches: S2 ────────────────────────────────────────────────
    print("\n── נושאים (Semantic Scholar) ──")
    for q in TOPIC_QUERIES_S2:
        print(f"  🔍 {q[:55]}")
        res = _s2_search(q, days=90)
        print(f"     S2: {len(res)}")
        all_papers.extend(res)
        time.sleep(3.5)

    # ── 3. Topic searches: arXiv ─────────────────────────────────────────────
    print("\n── נושאים (arXiv) ──")
    for q in TOPIC_QUERIES_ARXIV:
        print(f"  🔍 {q[:55]}")
        res = _arxiv_search(f"all:{q}", days=90)
        print(f"     arXiv: {len(res)}")
        all_papers.extend(res)
        time.sleep(2.0)

    # ── Enrich & deduplicate ─────────────────────────────────────────────────
    all_papers = _dedup(all_papers)
    print(f"\n  ✅ {len(all_papers)} מאמרים ייחודיים — מעבד...")

    for p in all_papers:
        cls            = _classify(p)
        p["_cls"]      = cls
        p["status"]    = cls["status"]
        p["matched"]   = cls["matched"]
        p["priority"]  = cls["priority"]
        p["score"]     = _score(p, cls)
        p["stardust"]  = _stardust(p)
        p["summary_he"]= _hebrew_summary(p, cls)

    all_papers.sort(key=lambda p: (0 if p["priority"]=="red" else 1,
                                   -p["score"],
                                   p.get("date") or "0000-00-00"))

    # ── Save JSON ─────────────────────────────────────────────────────────────
    export = [{k: v for k, v in p.items() if k != "_cls"} for p in all_papers]
    alerts = sum(1 for p in export if p["priority"] == "red")
    output = {
        "generated_at":  now.strftime("%d/%m/%Y %H:%M"),
        "generated_iso": now.isoformat(),
        "total":         len(export),
        "alerts":        alerts,
        "papers":        export,
    }
    DATA_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  → search_results.json ({DATA_FILE.stat().st_size//1024} KB)")

    # ── Generate dashboard ────────────────────────────────────────────────────
    print("  📊 בונה dashboard...")
    _html(all_papers, now.strftime("%d/%m/%Y %H:%M"))

    print(f"\n✅ [{now.strftime('%H:%M')}] הושלם — {len(export)} מאמרים, {alerts} התראות מיידיות")


if __name__ == "__main__":
    main()
