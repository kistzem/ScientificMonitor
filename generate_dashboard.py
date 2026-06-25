#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_dashboard.py — builds the 12-tab ScientificMonitor dashboard.html."""

import io, json, sys
from datetime import datetime
from pathlib import Path
import pytz

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)

SCRIPT_DIR = Path(__file__).parent.resolve()
ISRAEL_TZ  = pytz.timezone("Asia/Jerusalem")
PORT       = 5759


def _load(fname):
    p = SCRIPT_DIR / "data" / fname
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def generate():
    now  = datetime.now(ISRAEL_TZ)

    acad  = _load("academics_latest.json")
    comp  = _load("competition_latest.json")
    field = _load("papers_latest.json")
    pre   = _load("preprints_latest.json")
    cls   = _load("classified_latest.json")
    net   = _load("network_latest.json")
    cit   = _load("citations_latest.json")
    trnd  = _load("trends_latest.json")
    fund  = _load("funding_latest.json")
    contr = _load("controversies_latest.json")
    conf  = _load("conferences_latest.json")
    pol   = _load("policy_latest.json")
    anom  = _load("anomalies_latest.json")
    retr  = _load("retractions_latest.json")
    neg   = _load("negatives_latest.json")
    saved = _load("saved_papers.json")

    cats  = cls.get("categories", {})

    data = {
        "generated_at":       now.strftime("%d/%m/%Y %H:%M"),
        "port":               PORT,
        "academia":           acad.get("papers", []),
        "competition":        comp.get("papers", []),
        "field":              field.get("papers", []),
        "preprints":          pre.get("papers", []),
        "contradictions":     cats.get("contradiction", []),
        "network":            net,
        "citations":          cit.get("citation_data", []),
        "citation_alerts":    cit.get("trajectory_alerts", []),
        "trends":             trnd,
        "funding":            fund.get("items", []),
        "controversies":      contr.get("controversies", []),
        "conferences":        conf.get("papers", []),
        "policy":             pol.get("items", []),
        "anomalies":          anom.get("anomalies", []),
        "retractions":        retr.get("retractions", []),
        "negatives":          neg.get("findings", []),
        "alerts_immediate":   cls.get("alerts_immediate", []),
        "saved_ids":          saved.get("ids", []),
        "stats": {
            "academia":    len(acad.get("papers", [])),
            "competition": len(comp.get("papers", [])),
            "preprints":   len(pre.get("papers", [])),
            "controversies": contr.get("total", 0),
            "anomalies":   anom.get("total", 0),
            "policy_risks": pol.get("risk_count", 0),
            "new_academic": acad.get("new_count", 0),
        },
    }
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    html = f"""<!DOCTYPE html>
<html dir="rtl" lang="he">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>ScientificMonitor — SAI/SRM Intelligence</title>
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;overflow:hidden;font-family:'Segoe UI',Arial,sans-serif;font-size:13px;background:#08111e;color:#c8d8e8;direction:rtl}}
#app{{display:flex;flex-direction:column;height:100%}}
/* Header */
#hdr{{background:linear-gradient(135deg,#0a1a2e,#0f2540);border-bottom:1px solid #1a3555;padding:9px 16px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}}
#hdr h1{{font-size:14px;font-weight:700;color:#5bc8fa;letter-spacing:.3px}}
.hdr-right{{display:flex;align-items:center;gap:10px;font-size:11px;color:#4a6a8a}}
/* Alert banner */
#alert-banner{{display:none;background:#5c1212;border-bottom:2px solid #e74c3c;padding:5px 16px;font-size:11.5px;color:#ffcccc;flex-shrink:0;cursor:pointer}}
#alert-banner.show{{display:block}}
/* Summary */
#summary-bar{{background:#0b1c2e;border-bottom:1px solid #162840;padding:6px 16px;display:flex;gap:14px;align-items:center;flex-shrink:0;flex-wrap:wrap}}
.kpi{{text-align:center}}
.kpi .val{{font-size:14px;font-weight:700}}
.kpi .lbl{{font-size:10px;color:#4a6a8a;margin-top:1px}}
.kpi-sep{{width:1px;background:#162840;height:26px}}
/* Tabs */
#tabs{{display:flex;background:#0c1c2e;border-bottom:1px solid #162840;flex-shrink:0;overflow-x:auto}}
.tab-btn{{flex-shrink:0;padding:7px 10px;border:none;background:none;color:#4a6a8a;font-size:11px;font-weight:600;cursor:pointer;border-bottom:3px solid transparent;transition:all .15s;font-family:inherit;white-space:nowrap}}
.tab-btn:hover{{color:#c8d8e8;background:#0f2030}}
.tab-btn.active{{color:#5bc8fa;border-bottom-color:#5bc8fa;background:#0a1628}}
.bdg{{background:#e74c3c;color:#fff;border-radius:10px;padding:1px 4px;font-size:9px;margin-right:2px;vertical-align:top}}
.bdg-org{{background:#e67e22}}
/* Content */
#content{{flex:1;overflow-y:auto;background:#f0f3f7;color:#1e2e40;scrollbar-width:thin}}
.view-hdr{{background:#fff;padding:10px 16px 8px;border-bottom:2px solid #e2e8f0;display:flex;justify-content:space-between;align-items:center}}
.view-hdr h2{{font-size:14px;font-weight:700;color:#0f2540}}
.view-hdr p{{font-size:11px;color:#6b8099;margin-top:2px}}
/* Tables */
.tbl-wrap{{padding:8px 14px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:#0f2540;color:#fff;padding:6px 9px;text-align:right;white-space:nowrap;font-weight:600}}
td{{padding:6px 9px;border-bottom:1px solid #e5eaf0;vertical-align:top}}
tr:hover td{{background:#eef3fa}}
/* Chips and badges */
.chip{{display:inline-block;padding:1px 6px;border-radius:10px;font-size:10px;font-weight:700;margin:1px}}
.chip-red{{background:#fde8e8;color:#b00}} .chip-org{{background:#fef0e0;color:#a60}}
.chip-green{{background:#e8f8ee;color:#060}} .chip-blue{{background:#e8f4ff;color:#036}}
.chip-purple{{background:#f2e8ff;color:#60a}}
.score-badge{{display:inline-block;width:20px;height:20px;border-radius:50%;font-size:10px;font-weight:700;text-align:center;line-height:20px}}
.s-hi{{background:#27ae60;color:#fff}} .s-med{{background:#f39c12;color:#fff}} .s-lo{{background:#95a5a6;color:#fff}}
/* Alert boxes */
.alert-box{{margin:8px 14px;padding:8px 12px;border-radius:7px;font-size:12px;border-left:4px solid}}
.alert-box.critical{{background:#fdf0ef;border-color:#c0392b;color:#7b1a1a}}
.alert-box.error{{background:#fdf3ef;border-color:#e74c3c;color:#7b2020}}
.alert-box.warning{{background:#fef9ec;border-color:#f39c12;color:#7b5900}}
.alert-box.info{{background:#eaf4fb;border-color:#3498db;color:#1a4a6a}}
.alert-box.success{{background:#eafaf1;border-color:#27ae60;color:#0f3a1e}}
/* Buttons */
.btn{{padding:3px 9px;border:none;border-radius:4px;font-size:11px;cursor:pointer;font-family:inherit;font-weight:600;margin:1px}}
.btn-primary{{background:#3498db;color:#fff}} .btn-primary:hover{{background:#2980b9}}
.btn-success{{background:#27ae60;color:#fff}} .btn-success:hover{{background:#1e8449}}
.btn-saved{{background:#8e44ad;color:#fff}}
.btn-warn{{background:#e67e22;color:#fff}}
.btn-danger{{background:#e74c3c;color:#fff}}
/* Search */
input.search-inp{{padding:4px 9px;border:1px solid #c5d0dc;border-radius:5px;font-size:12px;width:180px;font-family:inherit}}
input.search-inp:focus{{outline:none;border-color:#3498db}}
/* Network viz */
#net-wrap{{padding:10px 14px;height:360px;overflow:hidden;position:relative}}
#net-canvas{{width:100%;height:100%;border-radius:8px;background:#f8fafc}}
/* Trend chart */
.trend-bar{{height:8px;background:#3498db;border-radius:4px;display:inline-block;min-width:2px}}
.empty{{text-align:center;color:#8a9ab0;padding:24px;font-size:13px}}
/* Status indicator */
.status-new{{color:#27ae60;font-weight:700}} .status-contr{{color:#e74c3c;font-weight:700}}
.status-comp{{color:#e67e22;font-weight:700}} .status-opp{{color:#3498db;font-weight:700}}
</style>
</head>
<body>
<div id="app">

<div id="hdr">
  <h1>🔬 ScientificMonitor — SAI/SRM Intelligence Platform</h1>
  <div class="hdr-right">
    <span id="hdr-time">{now.strftime('%d/%m/%Y %H:%M')}</span>
    <span>|</span>
    <span>localhost:{PORT}</span>
    <button class="btn btn-primary" onclick="refreshAll()" id="refresh-btn">🔄 עדכן הכל</button>
    <span id="refresh-status" style="font-size:10px;max-width:200px"></span>
  </div>
</div>

<div id="alert-banner" onclick="switchTab('academia',null)"></div>

<div id="summary-bar">
  <div class="kpi"><div class="val" id="sb-acad" style="color:#5bc8fa">—</div><div class="lbl">מאמרים אקדמיה</div></div>
  <div class="kpi-sep"></div>
  <div class="kpi"><div class="val" id="sb-pre">—</div><div class="lbl">Preprints</div></div>
  <div class="kpi-sep"></div>
  <div class="kpi"><div class="val" id="sb-comp" style="color:#e67e22">—</div><div class="lbl">תחרות</div></div>
  <div class="kpi-sep"></div>
  <div class="kpi"><div class="val" id="sb-contr" style="color:#e74c3c">—</div><div class="lbl">מחלוקות</div></div>
  <div class="kpi-sep"></div>
  <div class="kpi"><div class="val" id="sb-anom" style="color:#e67e22">—</div><div class="lbl">אנומליות</div></div>
  <div class="kpi-sep"></div>
  <div class="kpi"><div class="val" id="sb-pol" style="color:#9b59b6">—</div><div class="lbl">מדיניות</div></div>
</div>

<div id="tabs">
  <button class="tab-btn active" onclick="switchTab('academia',this)">🔴 אקדמיה<span id="bdg-academia" class="bdg" style="display:none"></span></button>
  <button class="tab-btn" onclick="switchTab('competition',this)">🟡 תחרות<span id="bdg-competition" class="bdg bdg-org" style="display:none"></span></button>
  <button class="tab-btn" onclick="switchTab('preprints',this)">📄 Preprints<span id="bdg-preprints" class="bdg" style="display:none"></span></button>
  <button class="tab-btn" onclick="switchTab('controversies',this)">⚔️ מחלוקות<span id="bdg-controversies" class="bdg" style="display:none"></span></button>
  <button class="tab-btn" onclick="switchTab('network',this)">🕸 Network</button>
  <button class="tab-btn" onclick="switchTab('citations',this)">📊 Citations<span id="bdg-citations" class="bdg" style="display:none"></span></button>
  <button class="tab-btn" onclick="switchTab('trends',this)">📈 Trends</button>
  <button class="tab-btn" onclick="switchTab('funding',this)">💰 מימון</button>
  <button class="tab-btn" onclick="switchTab('patents',this)">📋 פטנטים</button>
  <button class="tab-btn" onclick="switchTab('conferences',this)">🎓 כנסים</button>
  <button class="tab-btn" onclick="switchTab('policy',this)">⚖️ מדיניות<span id="bdg-policy" class="bdg" style="display:none"></span></button>
  <button class="tab-btn" onclick="switchTab('anomalies',this)">🔍 Anomalies<span id="bdg-anomalies" class="bdg" style="display:none"></span></button>
  <button class="tab-btn" onclick="switchTab('saved',this)">⭐ שמור</button>
</div>

<div id="content"></div>
</div>

<script>
const DATA = {data_json};
const $ = id => document.getElementById(id);
let _tab = 'academia';
let _savedIds = new Set(DATA.saved_ids || []);
let _searchQ  = '';

/* ── Init ─────────────────────────────────────────────────────────── */
function init() {{
  const s = DATA.stats || {{}};
  $('sb-acad').textContent = s.academia || 0;
  $('sb-pre').textContent  = s.preprints || 0;
  $('sb-comp').textContent = s.competition || 0;
  $('sb-contr').textContent = s.controversies || 0;
  $('sb-anom').textContent  = s.anomalies || 0;
  $('sb-pol').textContent   = (DATA.policy||[]).filter(p=>p.risk_level==='high').length;

  const setBdg = (id, n, cls) => {{
    const el = $('bdg-'+id);
    if(el && n>0) {{ el.textContent=n; el.style.display=''; if(cls) el.className='bdg '+cls; }}
  }};
  setBdg('academia',    s.new_academic || s.academia);
  setBdg('competition', s.competition);
  setBdg('preprints',   DATA.preprints.filter(p=>p.is_new).length);
  setBdg('controversies', s.controversies);
  setBdg('policy',      (DATA.policy||[]).filter(p=>p.risk_level==='high').length);
  setBdg('anomalies',   (DATA.anomalies||[]).filter(a=>a.severity==='high').length);
  setBdg('citations',   (DATA.citation_alerts||[]).length);

  // Alert banner
  const imm = DATA.alerts_immediate || [];
  if(imm.length) {{
    const ban = $('alert-banner');
    ban.innerHTML = `🔴 ${{imm.length}} התראות מיידיות: `+
      imm.slice(0,3).map(a=>`<b>${{a.author||''}}</b>: "${{(a.title||'').slice(0,50)}}..."`).join(' | ')+
      ' — לחץ לפרטים';
    ban.classList.add('show');
  }}

  renderTab();
}}

function switchTab(tab, btn) {{
  _tab = tab; _searchQ = '';
  document.querySelectorAll('.tab-btn').forEach(b=>b.classList.remove('active'));
  if(btn) btn.classList.add('active');
  else document.querySelectorAll('.tab-btn').forEach(b=>{{
    if(b.getAttribute('onclick')&&b.getAttribute('onclick').includes("'"+tab+"'")) b.classList.add('active');
  }});
  renderTab();
}}

function renderTab() {{
  const fns = {{
    academia:      () => renderPapers(DATA.academia,   '🔴 מאמרים חדשים — חוקרים מעוקבים', 'academia'),
    competition:   () => renderPapers(DATA.competition,'🟡 עדכוני תחרות ואורגניזציות SAI', 'competition'),
    preprints:     () => renderPapers(DATA.preprints,  '📄 Preprints — arXiv / bioRxiv', 'preprints'),
    controversies: () => renderControversies(),
    network:       () => renderNetwork(),
    citations:     () => renderCitations(),
    trends:        () => renderTrends(),
    funding:       () => renderFunding(),
    patents:       () => renderPapers((DATA.field||[]).filter(p=>p.source==='patent'), '📋 פטנטים בתחום SAI', 'patents'),
    conferences:   () => renderPapers(DATA.conferences,'🎓 כנסים — מצגות ותקצירים', 'conferences'),
    policy:        () => renderPolicy(),
    anomalies:     () => renderAnomalies(),
    saved:         () => renderSaved(),
  }};
  $('content').innerHTML = (fns[_tab]||fns.academia)();
  $('content').scrollTop = 0;
  if(_tab==='network') drawNetwork();
  if(_tab==='trends')  drawTrends();
}}

/* ── Paper row ────────────────────────────────────────────────────── */
function paperRow(p) {{
  const score = p.relevance_score || 0;
  const sCls  = score>=8?'s-hi':score>=5?'s-med':'s-lo';
  const isSaved = _savedIds.has(p.id);
  const auth  = (p.authors||[]).slice(0,3).join(', ')+(p.authors&&p.authors.length>3?' +':'');
  const isNew = p.is_new ? '<span class="chip chip-green">חדש</span>' : '';
  const isContr = p.contradicts_stardust ? '<span class="chip chip-red">⚠️ סתירה</span>' : '';
  const trackedChip = p.tracked_author ? `<span class="chip chip-red">${{p.tracked_author}}</span>` :
                      p.tracked_org    ? `<span class="chip chip-org">${{p.tracked_org}}</span>` : '';
  const src   = {{arxiv:'📄',pubmed:'🏥',semantic_scholar:'🔬',patent:'📋',biorxiv:'🧬'}}[p.source]||'📄';
  const pdfBtn= p.pdf_url ? `<a href="${{p.pdf_url}}" target="_blank" class="btn btn-warn">PDF</a>` : '';
  const summary = (p.summary_he||'').split('\n')[0]||'';
  return `<tr>
    <td style="min-width:300px;max-width:400px">
      <a href="${{p.url}}" target="_blank" style="font-weight:700;color:#0f2540;text-decoration:none;font-size:12px">${{p.title||'—'}}</a>
      <div style="font-size:10px;color:#5d7a8a;margin-top:2px">${{auth}}</div>
      <div style="font-size:10px;color:#8a9ab0;font-style:italic;margin-top:1px">${{(p.abstract||'').slice(0,150)}}...</div>
      <div style="margin-top:3px">${{trackedChip}}${{isNew}}${{isContr}}</div>
    </td>
    <td style="white-space:nowrap;font-size:11px;color:#6b8099">${{p.published_date||'—'}}</td>
    <td style="font-size:11px">${{src}} ${{p.source}}</td>
    <td><span class="score-badge ${{sCls}}">${{score}}</span></td>
    <td style="white-space:nowrap">
      <a href="${{p.url}}" target="_blank" class="btn btn-primary">קרא</a>
      ${{pdfBtn}}
      <button class="btn ${{isSaved?'btn-saved':'btn-success'}}" onclick="toggleSave('${{p.id}}',this)">${{isSaved?'⭐':'☆'}}</button>
    </td>
  </tr>`;
}}

function renderPapers(papers, title, tab) {{
  papers = papers || [];
  const filtered = _searchQ ? papers.filter(p=>(p.title+' '+(p.authors||[]).join(' ')).toLowerCase().includes(_searchQ)) : papers;
  const rows = filtered.map(p=>paperRow(p)).join('') ||
    `<tr><td colspan="5" class="empty">אין מאמרים${{_searchQ?' עבור "'+_searchQ+'"':''}}</td></tr>`;
  return `<div class="view-hdr">
    <div><h2>${{title}}</h2><p>עודכן: ${{DATA.generated_at}} · ${{filtered.length}} מאמרים</p></div>
    <input class="search-inp" placeholder="חיפוש..." oninput="_searchQ=this.value.toLowerCase();renderTab()">
  </div>
  <div class="tbl-wrap"><table>
  <thead><tr><th>כותרת + מחברים</th><th>תאריך</th><th>מקור</th><th>ציון</th><th>פעולות</th></tr></thead>
  <tbody>${{rows}}</tbody></table></div>`;
}}

/* ── Controversies ────────────────────────────────────────────────── */
function renderControversies() {{
  const items = DATA.controversies || [];
  if(!items.length) return `<div class="view-hdr"><h2>⚔️ מחלוקות בתחום SAI</h2></div>
    <div class="alert-box success" style="margin:18px">✅ לא נמצאו מחלוקות ישירות</div>`;
  const html = items.map(c=>{{
    const imp = c.stardust_impact==='high' ? '<span class="chip chip-red">⚠️ השלכה לStardust</span>' : '';
    const phrases = (c.disagreement_phrases||[]).slice(0,2).join(', ');
    const conflicts = (c.conflicting_with||[]).slice(0,1).map(cf=>
      `<div style="font-size:10px;color:#8b3a3a;margin-top:3px">↔️ סותר: ${{cf.opposing_paper_title||''}}</div>`
    ).join('');
    return `<tr>
      <td><a href="${{c.url||'#'}}" target="_blank" style="font-weight:700;color:#0f2540">${{c.title||'—'}}</a>
          <div style="font-size:10px;color:#5d7a8a">${{(c.authors||[]).slice(0,2).join(', ')}}</div>
          ${{conflicts}}
          <div style="margin-top:3px">${{imp}}</div></td>
      <td style="font-size:11px">${{c.published_date||'—'}}</td>
      <td style="font-size:11px;color:#7b2020;max-width:200px">${{phrases}}</td>
      <td><a href="${{c.url||'#'}}" target="_blank" class="btn btn-primary">קרא</a></td>
    </tr>`;
  }}).join('');
  return `<div class="view-hdr"><h2>⚔️ מחלוקות ודעות נוגדות (${{items.length}})</h2>
    <p>מאמרים המציגים ממצאים סותרים או ביקורת ישירה</p></div>
  <div class="tbl-wrap"><table>
  <thead><tr><th>מאמר</th><th>תאריך</th><th>ביטויי מחלוקת</th><th>פעולות</th></tr></thead>
  <tbody>${{html}}</tbody></table></div>`;
}}

/* ── Network ──────────────────────────────────────────────────────── */
function renderNetwork() {{
  const net = DATA.network || {{}};
  const hubs = net.hubs || [];
  const recollabs = net.recent_collabs || [];
  const hubRows = hubs.map(h=>
    `<tr><td><b>${{h.name}}</b></td><td>${{h.degree}}</td><td>${{h.total_collab_count}}</td>
     <td>${{h.is_tracked?'<span class="chip chip-red">מעוקב</span>':''}}</td></tr>`
  ).join('') || `<tr><td colspan="4" class="empty">אין נתוני רשת — הרץ עדכון</td></tr>`;
  const colRows = recollabs.map(c=>
    `<tr><td style="font-size:11px">${{c.title}}</td><td style="font-size:11px">${{(c.authors||[]).slice(0,3).join(', ')}}</td>
     <td style="font-size:11px">${{c.date}}</td></tr>`
  ).join('');
  const stardust = net.stardust_position;
  const stardustHtml = stardust ?
    `<div class="alert-box info" style="margin:10px 14px">🌟 מיקום Stardust ברשת: <b>${{stardust.name}}</b> — ${{stardust.degree}} שיתופי פעולה (${{stardust.papers_count}} מאמרים)</div>` : '';
  return `<div class="view-hdr"><h2>🕸 מפת הרשת — Co-authorship Network</h2>
    <p>${{net.node_count||0}} חוקרים · ${{net.edge_count||0}} קשרים · ${{net.cluster_count||0}} קלאסטרים · עודכן: ${{DATA.generated_at}}</p></div>
  ${{stardustHtml}}
  <div id="net-wrap"><canvas id="net-canvas"></canvas></div>
  <div class="tbl-wrap">
    <div style="display:flex;gap:16px;flex-wrap:wrap">
      <div style="flex:1;min-width:280px">
        <div style="font-weight:700;color:#0f2540;margin-bottom:6px">🏆 Hubs — חוקרים מרכזיים</div>
        <table><thead><tr><th>שם</th><th>Degree</th><th>שיתופים</th><th></th></tr></thead>
        <tbody>${{hubRows}}</tbody></table>
      </div>
      <div style="flex:1;min-width:280px">
        <div style="font-weight:700;color:#0f2540;margin-bottom:6px">🤝 שיתופי פעולה אחרונים</div>
        <table><thead><tr><th>מאמר</th><th>מחברים</th><th>תאריך</th></tr></thead>
        <tbody>${{colRows}}</tbody></table>
      </div>
    </div>
  </div>`;
}}

function drawNetwork() {{
  const c = document.getElementById('net-canvas');
  if(!c) return;
  const net = DATA.network || {{}};
  const nodes = (net.nodes || []).slice(0,50);
  if(!nodes.length) return;
  c.width  = c.parentElement.offsetWidth || 600;
  c.height = c.parentElement.offsetHeight || 340;
  const ctx = c.getContext('2d');
  const W=c.width, H=c.height;
  ctx.clearRect(0,0,W,H);
  ctx.fillStyle='#f8fafc'; ctx.fillRect(0,0,W,H);

  // Place nodes in circle
  const positions = {{}};
  nodes.forEach((node,i)=>{{
    const angle = (i/nodes.length)*Math.PI*2;
    const r = Math.min(W,H)*0.38;
    positions[node.name] = {{x: W/2+r*Math.cos(angle), y: H/2+r*Math.sin(angle)}};
  }});

  // Draw top connections
  nodes.slice(0,20).forEach(node=>{{
    (node.top_collabs||[]).slice(0,2).forEach(([collab])=>{{
      const p1 = positions[node.name];
      const p2 = positions[collab];
      if(p1&&p2){{
        ctx.strokeStyle='rgba(91,200,250,0.25)'; ctx.lineWidth=1;
        ctx.beginPath(); ctx.moveTo(p1.x,p1.y); ctx.lineTo(p2.x,p2.y); ctx.stroke();
      }}
    }});
  }});

  // Draw nodes
  nodes.forEach(node=>{{
    const pos = positions[node.name];
    if(!pos) return;
    const r = Math.max(4, Math.min(12, 3+node.degree*0.7));
    ctx.beginPath(); ctx.arc(pos.x,pos.y,r,0,Math.PI*2);
    ctx.fillStyle = node.is_tracked ? '#e74c3c' : '#3498db';
    ctx.fill();
    if(node.degree>=3){{
      ctx.fillStyle='#1e2e40'; ctx.font=`9px Segoe UI`;
      const nameShort = node.name.split(' ').pop()||node.name;
      ctx.fillText(nameShort.slice(0,10), pos.x+r+2, pos.y+3);
    }}
  }});
}}

/* ── Citations ────────────────────────────────────────────────────── */
function renderCitations() {{
  const data = DATA.citations || [];
  const alerts = DATA.citation_alerts || [];
  if(!data.length) return `<div class="view-hdr"><h2>📊 Citation Intelligence</h2></div>
    <div class="alert-box info" style="margin:18px">אין נתוני ציטוטים — הרץ עדכון</div>`;
  const alertHtml = alerts.map(a=>
    `<div class="alert-box warning" style="margin:6px 14px">📈 ${{a.msg_he}}</div>`
  ).join('');
  const rows = data.map(d=>{{
    const topCiting = (d.citations||[]).slice(0,3).map(c=>
      `<a href="${{c.url||'#'}}" target="_blank" style="font-size:10px;display:block;color:#3498db">${{(c.citing_title||'').slice(0,60)}}</a>`
    ).join('');
    return `<tr>
      <td><b>${{(d.paper_title||'').slice(0,70)}}</b>
          <div style="font-size:10px;color:#5d7a8a">${{d.tracked_author}}</div></td>
      <td style="text-align:center;font-size:14px;font-weight:700;color:${{d.citation_count>=10?'#27ae60':d.citation_count>=5?'#f39c12':'#95a5a6'}}">${{d.citation_count}}</td>
      <td>${{topCiting||'—'}}</td>
    </tr>`;
  }}).join('');
  return `<div class="view-hdr"><h2>📊 Citation Intelligence</h2>
    <p>עודכן: ${{DATA.generated_at}} · מעקב אחרי ${{data.length}} מאמרים</p></div>
  ${{alertHtml}}
  <div class="tbl-wrap"><table>
  <thead><tr><th>מאמר</th><th>ציטוטים</th><th>מצטטים נבחרים</th></tr></thead>
  <tbody>${{rows}}</tbody></table></div>`;
}}

/* ── Trends ───────────────────────────────────────────────────────── */
function renderTrends() {{
  const t = DATA.trends || {{}};
  const hot = t.hot_topics || [];
  const pivots = t.pivots || [];
  const active = t.most_active_authors || [];
  const labels = t.subtopic_labels || {{}};
  const counts = t.subtopic_counts || {{}};
  const maxC = Math.max(...Object.values(counts), 1);

  const countRows = Object.entries(counts).sort((a,b)=>b[1]-a[1]).map(([k,v])=>
    `<tr><td>${{labels[k]||k}}</td>
     <td><div class="trend-bar" style="width:${{Math.round(v/maxC*160)}}px"></div></td>
     <td style="font-weight:700">${{v}}</td></tr>`
  ).join('');

  const hotHtml = hot.map(h=>
    `<div class="alert-box warning" style="margin:4px 14px">🔥 ${{labels[h.topic]||h.topic}} — עלייה של +${{h.change_pct}}% (${{h.count}} מאמרים)</div>`
  ).join('') || `<div style="padding:10px 14px;color:#6b8099;font-size:12px">אין נושאים חמים חדשים</div>`;

  const pivotRows = pivots.map(p=>
    `<tr><td><a href="${{p.url}}" target="_blank" style="color:#0f2540">${{p.title}}</a></td>
     <td style="font-size:10px">${{(p.authors||[]).slice(0,2).join(', ')}}</td>
     <td style="font-size:10px;color:#e67e22">${{(p.signals||[]).join(', ')}}</td></tr>`
  ).join('');

  const activeRows = active.slice(0,8).map(a=>
    `<tr><td><b>${{a.name}}</b></td><td style="font-weight:700;color:#3498db">${{a.count}}</td></tr>`
  ).join('');

  return `<div class="view-hdr"><h2>📈 Trend Detection</h2>
    <p>עודכן: ${{DATA.generated_at}} · ${{t.total_papers||0}} מאמרים נותחו</p></div>
  <div style="padding:10px 14px"><div style="font-weight:700;color:#0f2540;margin-bottom:6px">🔥 נושאים חמים</div>${{hotHtml}}</div>
  <div class="tbl-wrap" style="display:flex;gap:14px;flex-wrap:wrap;padding:8px 14px">
    <div style="flex:1;min-width:260px">
      <div style="font-weight:700;color:#0f2540;margin-bottom:6px">📊 התפלגות נושאים</div>
      <table><thead><tr><th>נושא</th><th>פעילות</th><th>מאמרים</th></tr></thead>
      <tbody>${{countRows}}</tbody></table>
    </div>
    <div style="flex:1;min-width:200px">
      <div style="font-weight:700;color:#0f2540;margin-bottom:6px">👤 חוקרים פעילים</div>
      <table><thead><tr><th>שם</th><th>מאמרים</th></tr></thead>
      <tbody>${{activeRows}}</tbody></table>
    </div>
  </div>
  ${{pivots.length ? `<div class="tbl-wrap"><div style="font-weight:700;color:#0f2540;margin-bottom:6px">🔄 שינויי עמדה</div>
    <table><thead><tr><th>מאמר</th><th>מחברים</th><th>אות</th></tr></thead>
    <tbody>${{pivotRows}}</tbody></table></div>` : ''}}`;
}}

function drawTrends() {{ /* placeholder */ }}

/* ── Funding ──────────────────────────────────────────────────────── */
function renderFunding() {{
  const items = DATA.funding || [];
  if(!items.length) return `<div class="view-hdr"><h2>💰 מימון SAI</h2></div>
    <div class="alert-box info" style="margin:18px">אין נתוני מימון — הרץ עדכון</div>`;
  const rows = items.map(f=>{{
    const funders = (f.funders||[]).join(', ').slice(0,80);
    const typeCls = f.funder_type==='government'?'chip-blue':f.funder_type==='private'?'chip-purple':'chip-green';
    return `<tr>
      <td><a href="${{f.url||'#'}}" target="_blank" style="font-weight:700;color:#0f2540;font-size:12px">${{f.title||'—'}}</a>
          <div style="font-size:10px;color:#5d7a8a">${{(f.authors||[]).slice(0,2).join(', ')}}</div></td>
      <td style="font-size:11px;max-width:180px">${{funders}}</td>
      <td><span class="chip ${{typeCls}}">${{f.funder_type==='government'?'ממשלתי':f.funder_type==='private'?'פרטי':'לא ידוע'}}</span></td>
      <td style="font-size:11px">${{f.published_date||'—'}}</td>
      <td><a href="${{f.url||'#'}}" target="_blank" class="btn btn-primary">קרא</a></td>
    </tr>`;
  }}).join('');
  return `<div class="view-hdr"><h2>💰 מימון וקרנות SAI (${{items.length}})</h2>
    <p>עודכן: ${{DATA.generated_at}}</p></div>
  <div class="tbl-wrap"><table>
  <thead><tr><th>כותר</th><th>מממן</th><th>סוג</th><th>תאריך</th><th>פעולות</th></tr></thead>
  <tbody>${{rows}}</tbody></table></div>`;
}}

/* ── Policy ───────────────────────────────────────────────────────── */
function renderPolicy() {{
  const items = DATA.policy || [];
  const risks = items.filter(p=>p.risk_level==='high');
  const opps  = items.filter(p=>p.risk_level==='opportunity');
  const riskHtml = risks.map(p=>
    `<div class="alert-box critical" style="margin:5px 14px">
      🔴 <a href="${{p.url}}" target="_blank" style="color:#7b1a1a;font-weight:700">${{p.title||''}}</a>
      <div style="font-size:10px;margin-top:2px">${{(p.abstract||'').slice(0,150)}}</div>
    </div>`
  ).join('');
  const oppHtml = opps.map(p=>
    `<div class="alert-box success" style="margin:5px 14px">
      🟢 <a href="${{p.url}}" target="_blank" style="color:#0f3a1e;font-weight:700">${{p.title||''}}</a>
    </div>`
  ).join('');
  const rows = items.filter(p=>p.risk_level==='neutral').map(p=>
    `<tr><td><a href="${{p.url}}" target="_blank" style="font-weight:700;color:#0f2540">${{p.title||'—'}}</a></td>
     <td style="font-size:11px">${{(p.authors||[]).slice(0,2).join(', ')}}</td>
     <td style="font-size:11px">${{p.published_date||'—'}}</td>
     <td><a href="${{p.url||'#'}}" target="_blank" class="btn btn-primary">קרא</a></td></tr>`
  ).join('');
  return `<div class="view-hdr"><h2>⚖️ מדיניות ורגולציה (${{items.length}})</h2>
    <p>עודכן: ${{DATA.generated_at}} · ${{risks.length}} סיכונים · ${{opps.length}} הזדמנויות</p></div>
  ${{risks.length ? `<div style="padding:5px 0">${{riskHtml}}</div>` : ''}}
  ${{opps.length ? `<div style="padding:5px 0">${{oppHtml}}</div>` : ''}}
  ${{rows ? `<div class="tbl-wrap"><table>
    <thead><tr><th>כותר</th><th>מחברים</th><th>תאריך</th><th>פעולות</th></tr></thead>
    <tbody>${{rows}}</tbody></table></div>` : ''}}
  ${{!items.length ? '<div class="alert-box info" style="margin:18px">אין נתוני מדיניות — הרץ עדכון</div>' : ''}}`;
}}

/* ── Anomalies ────────────────────────────────────────────────────── */
function renderAnomalies() {{
  const items = DATA.anomalies || [];
  if(!items.length) return `<div class="view-hdr"><h2>🔍 Anomaly Detection</h2></div>
    <div class="alert-box success" style="margin:18px">✅ לא זוהו אנומליות</div>`;
  const html = items.map(a=>{{
    const sevCls = a.severity==='high'?'critical':a.severity==='medium'?'warning':'info';
    const typeLbl = {{publication_gap:'📉 חוסר פרסום',new_collaboration:'🤝 שיתוף חדש',
                      ip_overlap:'⚠️ IP',burst_activity:'📈 פעילות גבוהה'}}[a.type]||'🔍';
    return `<div class="alert-box ${{sevCls}}" style="margin:5px 14px">
      ${{typeLbl}}: ${{a.msg_he||''}}
      ${{a.paper_url?`<a href="${{a.paper_url}}" target="_blank" class="btn btn-primary" style="margin-right:8px">קרא</a>`:''}}</div>`;
  }}).join('');
  return `<div class="view-hdr"><h2>🔍 Anomaly Detection (${{items.length}})</h2>
    <p>דפוסים חריגים בפרסום ושיתוף פעולה · עודכן: ${{DATA.generated_at}}</p></div>
  ${{html}}`;
}}

/* ── Saved ────────────────────────────────────────────────────────── */
function renderSaved() {{
  const all = [...(DATA.academia||[]),...(DATA.competition||[]),...(DATA.preprints||[]),
               ...(DATA.field||[]),...(DATA.conferences||[])];
  const saved = all.filter(p=>_savedIds.has(p.id));
  if(!saved.length) return `<div class="view-hdr"><h2>⭐ מאמרים שמורים</h2></div>
    <div class="alert-box info" style="margin:18px">אין מאמרים שמורים — לחץ ☆ כדי לשמור</div>`;
  return `<div class="view-hdr"><h2>⭐ מאמרים שמורים (${{saved.length}})</h2></div>
  <div class="tbl-wrap"><table>
  <thead><tr><th>כותרת + מחברים</th><th>תאריך</th><th>מקור</th><th>ציון</th><th>פעולות</th></tr></thead>
  <tbody>${{saved.map(p=>paperRow(p)).join('')}}</tbody></table></div>`;
}}

/* ── Save / Refresh ───────────────────────────────────────────────── */
async function toggleSave(id, btn) {{
  if(_savedIds.has(id)) {{ _savedIds.delete(id); btn.textContent='☆'; btn.className='btn btn-success'; }}
  else {{ _savedIds.add(id); btn.textContent='⭐'; btn.className='btn btn-saved'; }}
  try {{
    await fetch('http://localhost:{PORT}/save', {{
      method:'POST', headers:{{'Content-Type':'application/json'}},
      body: JSON.stringify({{id, saved: _savedIds.has(id)}})
    }});
  }} catch(e) {{}}
  if(_tab==='saved') renderTab();
}}

async function refreshAll() {{
  const btn = $('refresh-btn');
  const st  = $('refresh-status');
  if(btn) {{ btn.disabled=true; btn.textContent='⏳ מעדכן...'; }}
  st.textContent = '⏳ מריץ סוכנים...';
  const _poll = () => {{
    const poll = setInterval(async()=>{{
      try {{
        const s = await fetch('http://localhost:{PORT}/status');
        const j = await s.json();
        if(!j.running) {{ clearInterval(poll); st.textContent='✅'; setTimeout(()=>location.reload(),1500); }}
        else st.textContent='⏳ '+(j.output||[]).slice(-1)[0];
      }} catch{{}}
    }}, 3000);
  }};
  try {{
    const r = await fetch('http://localhost:{PORT}/refresh', {{method:'POST'}});
    const d = await r.json();
    if(d.error==='כבר רץ') {{ st.textContent='⏳ כבר רץ...'; _poll(); }}
    else if(d.status==='started') {{ st.textContent='⏳ רץ ברקע...'; _poll(); }}
    else {{ st.textContent='❌ '+d.error; if(btn){{btn.disabled=false;btn.textContent='🔄 עדכן הכל';}} }}
  }} catch(e) {{ st.textContent='❌ שגיאת חיבור'; if(btn){{btn.disabled=false;btn.textContent='🔄 עדכן הכל';}} }}
}}

init();
</script>
</body>
</html>"""

    out = SCRIPT_DIR / "dashboard.html"
    out.write_text(html, encoding="utf-8")
    kb = out.stat().st_size / 1024
    print(f"Dashboard -> {out.name}  ({kb:.0f} KB)")


if __name__ == "__main__":
    print("Building ScientificMonitor dashboard...")
    generate()
