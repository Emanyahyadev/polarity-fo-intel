"use strict";
/* ================= utilities ================= */
const $ = s => document.querySelector(s);
const esc = s => (s==null?"":String(s)).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const store = {
  get(k,f){ try{ return JSON.parse(localStorage.getItem(k)) ?? f; }catch{ return f; } },
  set(k,v){ try{ localStorage.setItem(k, JSON.stringify(v)); }catch{} }
};
let toastT;
function toast(msg){ const t=$("#toast"); t.textContent=msg; t.classList.add("show");
  clearTimeout(toastT); toastT=setTimeout(()=>t.classList.remove("show"),1600); }

import * as vis from "./visualizations.js";

/* ================= theme ================= */
function applyTheme(){
  const savedTheme = store.get("fo.theme", null);
  if(savedTheme) document.documentElement.dataset.theme = savedTheme;
}
function toggleTheme(){
  const cur = document.documentElement.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next; store.set("fo.theme", next);
}
applyTheme();
$("#theme").onclick = toggleTheme;
$("#settings-theme").onclick = toggleTheme;

/* ================= views / routing ================= */
// Every routable page section. Not all of these have a nav tab — "research" is
// reached via the "Ask the Intelligence" CTA rather than a persistent tab.
const viewEls = {
  home:     $("#view-home"),
  discover: $("#view-discover"),
  research: $("#view-research"),
  agent:    $("#view-agent"),
  saved:    $("#view-saved"),
};
// Nav tabs only — a subset of viewEls that actually has a topbar button. Home has
// no tab (reached via the brand mark or a CTA), matching a minimal top nav.
const tabs = {
  discover: $("#tab-discover"),
  agent:    $("#tab-agent"),
  research: $("#tab-research"),
  saved:    $("#tab-saved"),
};
const NAV_VIEWS = new Set(Object.keys(viewEls));
const settingsView = $("#view-settings");
const profileView = $("#view-profile");

const shellEl = document.querySelector(".shell");
function showView(name, opts={}){
  for(const [k,view] of Object.entries(viewEls)) view.classList.toggle("hide", k!==name);
  for(const [k,tab] of Object.entries(tabs)) tab.setAttribute("aria-selected", k===name);
  settingsView.classList.toggle("hide", name!=="settings");
  profileView.classList.toggle("hide", name!=="profile");
  shellEl.classList.toggle("home-mode", name==="home");
  if(NAV_VIEWS.has(name) && !opts.keepHash) history.replaceState(null,"","#/"+name);
  if(name==="discover") loadDirectory();
  if(name==="saved") renderSaved();
  if(name==="home") loadHome();
  window.scrollTo(0,0);
}
tabs.discover.onclick = () => showView("discover");
tabs.agent.onclick = () => showView("agent");
tabs.research.onclick = () => showView("research");
tabs.saved.onclick = () => showView("saved");
$("#settings-btn").onclick = () => showView("settings");
$("#portfolio-btn").onclick = () => showView("saved");
$("#brand-home").onclick = () => showView("home");

function openProfile(id){
  location.hash = `#/firm/${encodeURIComponent(id)}`;
}
$("#profile-back").onclick = () => { history.back(); };

window.addEventListener("hashchange", routeFromHash);
function routeFromHash(){
  const h = location.hash;
  const m = /^#\/firm\/(.+)$/.exec(h);
  if(m){ renderProfile(decodeURIComponent(m[1])); return; }
  const v = /^#\/(\w+)$/.exec(h);
  if(v && NAV_VIEWS.has(v[1])) showView(v[1], {keepHash:true});
}

/* ================= status + coverage (real, live-computed) ================= */
let STATS = null;
fetch("/health").then(r=>r.json()).then(d=>{
  $("#status-text").textContent = `${d.records} verified records`;
  $("#foot-text").innerHTML = `Every answer shows the sources behind it and how far they go. Anything the
    system could not confirm is left blank and labelled, never filled with a guess. This currently covers
    <span class="num">${d.records}</span> firms — a deliberately small set held to a strict evidence
    standard, not a full market directory. If the free language-model quota runs out, answers switch to a
    plainer format built straight from the stored fields; what the system is allowed to claim does not
    change.`;
}).catch(()=>{ $("#status-text").textContent = "offline"; });

function statsReady(){
  return STATS ? Promise.resolve(STATS) : fetch("/stats").then(r=>r.json()).then(s=>{ STATS=s; return s; });
}

statsReady().then(s=>{
  if(!s.records) return;
  const cov = s.coverage||{}, n = s.records;
  const bar = (lbl,val) => `<div class="stat-row"><span class="lbl">${lbl}</span>
    <span class="bar"><i style="width:${Math.round(100*val/n)}%"></i></span>
    <span class="num num">${val}/${n}</span></div>`;
  const t = s.type||{};
  $("#coverage").innerHTML =
    bar("Single-family", t["Single-Family Office"]||0) +
    bar("Multi-family", t["Multi-Family Office"]||0) +
    bar("Undetermined", t["Undetermined"]||0) +
    `<div style="height:8px"></div>` +
    bar("AUM on file", cov.aum||0) + bar("Principal", cov.principal||0) +
    bar("Website", cov.website||0) + bar("Signals", cov.signals||0) +
    `<div class="stat-row"><span class="lbl">Countries</span><span></span><span class="num num">${s.countries||"—"}</span></div>` +
    `<div class="stat-row"><span class="lbl">Data as of</span><span></span><span class="num num" style="width:auto">${esc(s.as_of||"")}</span></div>`;

  $("#settings-source").textContent =
    `${s.records} verified family-office records, last refreshed ${s.as_of||"—"}. Served entirely from the ` +
    `dataset behind this API — nothing here is looked up live from the open web at request time.`;
}).catch(()=>{ $("#coverage").innerHTML = `<div class="empty">Unavailable.</div>`; });

/* ================= HOME ================= */
let homeLoaded = false;

function loadHome(){
  statsReady().then(s=>{
    if(!s.records) return;
    const sourced = s.records - (s.evidence_strength?.no_sources ?? 0);
    const tiles = [
      [s.records, "Verified Family Offices"],
      [s.coverage?.principal ?? 0, "Decision-Makers"],
      [s.coverage?.signals ?? 0, "Investment Signals"],
      [sourced, "Sources Verified"],
    ];
    $("#home-stats").innerHTML = tiles.map(([val,label])=>
      `<div class="stat-item"><b class="num">${val}</b><span>${label}</span></div>`).join("");
    $("#settings-source").textContent =
      `${s.records} verified family-office records, last refreshed ${s.as_of||"—"}. Served entirely from the ` +
      `dataset behind this API — nothing here is looked up live from the open web at request time.`;
  }).catch(()=>{ $("#home-stats").innerHTML = ""; });

  if(homeLoaded) return;
  homeLoaded = true;
  loadRecords().then(rows => {
    vis.renderGlobe("vis-globe", rows);

    // Discover teaser: a small, real sample — prefer richer records so the teaser
    // is informative, but never invent a field a card doesn't actually have.
    const scored = [...rows].sort((a,b) =>
      (Number(!!b.aum)+Number(!!b.principal)+Number((b.investing_sectors||[]).length>0)) -
      (Number(!!a.aum)+Number(!!a.principal)+Number((a.investing_sectors||[]).length>0)));
    $("#teaser-cards").innerHTML = scored.slice(0,3).map(r => `
      <button class="teaser-card" data-id="${esc(r.fo_id)}">
        <div class="tc-top"><span class="tc-name">${esc(r.name)}</span>
          <span class="conf-dot" data-c="${esc(r.confidence)}">${esc(r.confidence)}</span></div>
        <div class="tc-meta">${esc(r.type)}${r.location?` · ${esc(r.location)}`:""}</div>
        ${r.aum?`<div class="tc-aum num">${esc(r.aum)}</div>`:""}
        ${(r.investing_sectors||[]).length?`<div class="tc-focus">${esc(r.investing_sectors[0])}</div>`:""}
      </button>`).join("");
    $("#teaser-cards").onclick = e => {
      const b = e.target.closest(".teaser-card"); if(b) openProfile(b.dataset.id);
    };

    // Capital activity: real dated signals pulled across records, most recent first.
    const withSignals = [];
    for(const r of rows) for(const sg of (r.signals||[]))
      if(sg.date) withSignals.push({firm:r.name, id:r.fo_id, ...sg});
    withSignals.sort((a,b)=> b.date.localeCompare(a.date));
    const rail = withSignals.slice(0,5);
    $("#activity-rail").innerHTML = rail.length ? rail.map(a => `
      <button class="activity-item" data-id="${esc(a.id)}">
        <span class="ai-firm">${esc(a.firm)}</span>
        <span class="ai-date num">${esc(a.date)}</span>
        <span class="ai-text">${esc(a.text)}</span>
      </button>`).join("")
      : `<div class="empty-state">No dated signals are on file yet.</div>`;
    $("#activity-rail").onclick = e => {
      const b = e.target.closest(".activity-item"); if(b) openProfile(b.dataset.id);
    };
  }).catch(()=>{});
}

$("#ai-teaser-run").onclick = async () => {
  const btn = $("#ai-teaser-run");
  btn.disabled = true; btn.textContent = "Searching verified records…";
  try{
    const res = await fetch("/query",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({query:"Which family offices have shown recent interest in healthcare?"})});
    const d = await res.json();
    if(d.answered === false){
      $("#ai-teaser-result").innerHTML = `<div class="answer abstain reveal" style="margin-top:16px"><p>${esc(d.answer)}</p></div>`;
    } else {
      const firms = (d.cards||[]).slice(0,3);
      $("#ai-teaser-result").innerHTML = `<div class="reveal" style="margin-top:18px">
        <p class="ai-insight">${esc((d.answer||"").split("\n")[0])}</p>
        <div class="ai-firms">${firms.map(c=>`
          <span class="ai-firm-chip">${esc(c.name)} <span class="conf-dot" data-c="${esc(c.confidence)}">${esc(c.confidence)}</span></span>`).join("")}</div>
        <button class="text-btn" id="ai-teaser-full">See the full answer with evidence →</button>
      </div>`;
      $("#ai-teaser-full").onclick = openAsk;
    }
  }catch{
    $("#ai-teaser-result").innerHTML = `<p class="panel-note" style="margin-top:14px">Could not reach the research service.</p>`;
  }finally{ btn.disabled = false; btn.textContent = "Run this example →"; }
};

const HOME_EXAMPLES = ["Healthcare", "Technology", "Real Estate", "Renewable Energy"];
$("#home-chips").innerHTML = HOME_EXAMPLES.map(e=>`<button class="chip">${esc(e)}</button>`).join("");
$("#home-chips").addEventListener("click", e=>{
  const c = e.target.closest(".chip"); if(!c) return;
  $("#home-q").value = `Family offices investing in ${c.textContent}`; runHomeAsk();
});
function runHomeAsk(){
  const val = $("#home-q").value.trim();
  showView("research");
  if(val){ $("#q").value = val; ask(); }
}
function openAsk(){ showView("research"); $("#q").focus(); }
$("#home-ask").onclick = runHomeAsk;
$("#home-q").addEventListener("keydown", e=>{ if(e.key==="Enter") runHomeAsk(); });
$("#hero-ask").onclick = openAsk;
$("#hero-explore").onclick = () => showView("discover");
$("#nav-ask").onclick = openAsk;
$("#discover-more").onclick = () => showView("discover");
$("#cta-ask").onclick = openAsk;
$("#cta-explore").onclick = () => showView("discover");

/* ================= session: recent + pins ================= */
function renderRecent(){
  const rs = store.get("fo.recent", []);
  $("#recent").innerHTML = rs.length
    ? rs.map(q=>`<li><button data-q="${esc(q)}" title="${esc(q)}">${esc(q)}</button></li>`).join("")
    : `<li class="empty">No queries yet.</li>`;
}
function pushRecent(q){
  let rs = store.get("fo.recent", []).filter(x=>x!==q); rs.unshift(q);
  store.set("fo.recent", rs.slice(0,8)); renderRecent();
  if(!$("#view-saved").classList.contains("hide")) renderSaved();
}
$("#recent").addEventListener("click", e=>{
  const b = e.target.closest("button[data-q]"); if(!b) return;
  showView("research"); $("#q").value = b.dataset.q; ask();
});
$("#clear-recent").onclick = () => { store.set("fo.recent", []); renderRecent(); renderSaved(); };

function renderPins(){
  const ps = store.get("fo.pins", []);
  $("#pins").innerHTML = ps.length
    ? ps.map(p=>`<li><button data-id="${esc(p.id)}" title="Open ${esc(p.name)}">★ ${esc(p.name)}</button></li>`).join("")
    : `<li class="empty">Pin records from results.</li>`;
  const badge = $("#portfolio-badge");
  badge.textContent = ps.length;
  badge.hidden = ps.length === 0;
}
$("#pins").addEventListener("click", e=>{
  const b = e.target.closest("button[data-id]"); if(!b) return;
  openProfile(b.dataset.id);
});
function togglePin(id, name, btn){
  let ps = store.get("fo.pins", []);
  const has = ps.some(p=>p.id===id);
  ps = has ? ps.filter(p=>p.id!==id) : [...ps, {id, name}];
  store.set("fo.pins", ps); renderPins();
  if(btn){ btn.setAttribute("aria-pressed", !has); btn.innerHTML = !has ? "★ Pinned" : "☆ Pin"; }
  toast(!has ? "Pinned" : "Unpinned");
  if(!$("#view-saved").classList.contains("hide")) renderSaved();
  return !has;
}
renderRecent(); renderPins();

/* ================= saved (pins + recent as a page) ================= */
function renderSaved(){
  const ps = store.get("fo.pins", []);
  $("#saved-pins").innerHTML = ps.length
    ? ps.map(p=>`<div class="saved-row" data-id="${esc(p.id)}">
        <span class="saved-name">${esc(p.name)}</span>
        <span class="saved-actions">
          <button class="text-btn" data-open="${esc(p.id)}">Open profile</button>
          <button class="text-btn" data-unpin="${esc(p.id)}">Unpin</button>
        </span></div>`).join("")
    : `<div class="empty">No pinned firms yet. Pin a firm from a research result, agent result, or the
        directory to save it here.</div>`;
  const rs = store.get("fo.recent", []);
  $("#saved-recent").innerHTML = rs.length
    ? rs.map(q=>`<div class="saved-row"><span class="saved-name">${esc(q)}</span>
        <span class="saved-actions"><button class="text-btn" data-rerun="${esc(q)}">Ask again</button></span></div>`).join("")
    : `<div class="empty">No queries yet this session.</div>`;
}
document.querySelector("#view-saved").addEventListener("click", e=>{
  const open = e.target.closest("button[data-open]");
  const unpin = e.target.closest("button[data-unpin]");
  const rerun = e.target.closest("button[data-rerun]");
  if(open) openProfile(open.dataset.open);
  else if(unpin){ togglePin(unpin.dataset.unpin, "", null); renderSaved(); }
  else if(rerun){ showView("research"); $("#q").value = rerun.dataset.rerun; ask(); }
});
$("#settings-clear").onclick = () => {
  store.set("fo.pins", []); store.set("fo.recent", []);
  renderPins(); renderRecent(); renderSaved(); toast("Local data cleared");
};

/* ================= example chips ================= */
const EXAMPLES = ["Multi-family offices in Texas","Family offices with AUM over $1 billion",
  "Single-family offices in Belgium","Tell me about WE Family Offices","Family offices in Florida"];
$("#chips").innerHTML = EXAMPLES.map(e=>`<button class="chip">${esc(e)}</button>`).join("");
$("#chips").addEventListener("click", e=>{
  const c = e.target.closest(".chip"); if(!c) return;
  $("#q").value = c.textContent; ask();
});

/* ================= answer rendering ================= */
const MODE = {
  llm:  ["llm","Synthesized · grounded","Generated by a language model: family-office concepts may be explained as general context, but every firm-specific fact comes from the verified records — any firm named outside them is rejected."],
  "extractive":          ["ext","Deterministic extract","Built directly from verified fields only — no generation. Used when no LLM is configured or its free-tier daily quota is exhausted."],
  "extractive-fallback": ["ext","Deterministic extract","The generated answer failed the grounding check and was replaced by a deterministic extract of verified fields."],
  abstain: ["abst","Declined","The retrieved evidence did not clear the grounding threshold, so the system declines rather than guessing."],
  count: ["ext","Deterministic count",""], total: ["ext","Deterministic total",""],
  compound: ["ext","Deterministic","" ], universal: ["ext","Deterministic coverage check",""],
};
function modeChip(m){
  const [cls,label,tip] = MODE[m] || ["ext",m,""];
  return `<span class="mode ${cls}" title="${esc(tip)}">${esc(label)}</span>`;
}

// Safe markdown-lite renderer: escape everything first, then re-introduce ONLY
// <strong>/<em>, bullet lists, and paragraphs. Stray pipe-tables (a model ignoring the
// format instruction) are flattened into readable label rows instead of raw pipes.
function inlineMD(s){
  return esc(s)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s).,;:!?]|$)/g, "$1<em>$2</em>");
}
function mdLite(text){
  const blocks = text.replace(/^#{1,6}\s*/gm, "").split(/\n{2,}/);
  const out = [];
  for(const block of blocks){
    const lines = block.split("\n").map(l=>l.trim()).filter(Boolean);
    if(!lines.length) continue;
    let list = [], para = [];
    const flushP = () => { if(para.length){ out.push(`<p>${para.map(inlineMD).join("<br>")}</p>`); para=[]; } };
    const flushL = () => { if(list.length){ out.push(`<ul class="md">${list.map(li=>`<li>${inlineMD(li)}</li>`).join("")}</ul>`); list=[]; } };
    for(const ln of lines){
      if(/^\|.*\|/.test(ln)){                                   // stray table row -> label row
        if(/^\|[\s\-:|]+\|$/.test(ln)) continue;                // drop |---|---| separators
        const cells = ln.split("|").map(c=>c.trim()).filter(Boolean);
        flushP(); list.push(cells.join(" — "));
      } else if(/^([-*•]|\d+[.)])\s+/.test(ln)){
        flushP(); list.push(ln.replace(/^([-*•]|\d+[.)])\s+/, ""));
      } else { flushL(); para.push(ln); }
    }
    flushP(); flushL();
  }
  return out.join("");
}
function answerHTML(d){
  const text = d.answer || "";
  // extractive answers arrive as "Found N…" + "• Firm — fact · fact" lines: render as rows
  if(text.includes("\n•") || text.startsWith("•")){
    const lines = text.split("\n").filter(Boolean);
    const lead = lines[0].startsWith("•") ? "" : `<p>${esc(lines[0])}</p>`;
    const items = [];
    for(const ln of lines){
      if(ln.startsWith("•")) items.push({main: ln.replace(/^•\s*/,""), subs: []});
      else if(ln.trim().startsWith("↳") && items.length)
        items[items.length-1].subs.push(ln.trim().replace(/^↳\s*/,""));
    }
    const list = items.map(it=>`<li>${esc(it.main)}${it.subs.map(s=>`<span class="sub">${esc(s)}</span>`).join("")}</li>`).join("");
    return lead + (list ? `<ul>${list}</ul>` : "");
  }
  return mdLite(text);
}

function factHTML(label, value, mono, sub){
  if(!value) return "";
  return `<div class="fact"><span class="micro">${label}</span>
    <span class="v${mono?" num":""}">${value}${sub?` <span class="role">${esc(sub)}</span>`:""}</span></div>`;
}

function signalRow(s){
  const text = typeof s === "string" ? s : s.text;
  const date = typeof s === "object" ? s.date : null;
  return `<div class="sig-row">${date?`<span class="sig-date num">${esc(date)}</span>`:""}<span>${esc(text)}</span></div>`;
}

function card(c, i){
  const conf = c.confidence || "Low";
  const typeCls = c.type === "Undetermined" ? "b-und" : "b-type";
  const nm = c.website
    ? `<a href="${esc(c.website)}" target="_blank" rel="noopener">${esc(c.name)}</a>` : esc(c.name);
  const phone = c.phone
    ? `<a href="tel:${esc(String(c.phone).replace(/[^+\d]/g,""))}" class="num">${esc(c.phone)}</a>` : "";
  const sigs = (c.signals||[]).slice(0,3).map(signalRow).join("");
  const pinned = store.get("fo.pins", []).some(p=>p.id===c.fo_id);
  return `<article class="card reveal" style="animation-delay:${Math.min(i*45,270)}ms" data-id="${esc(c.fo_id)}">
    <div class="head">
      <span class="name">${nm}</span>
      <span class="badges">
        <span class="badge ${typeCls}">${esc(c.type)}</span>
        <span class="conf-dot" data-c="${esc(conf)}" title="Overall record confidence — the weakest link across identity anchors, click into the profile for the evidence behind it">${esc(conf)}</span>
      </span>
    </div>
    <div class="facts">
      ${factHTML("Location", esc(c.location))}
      ${factHTML("AUM", esc(c.aum), true)}
      ${factHTML("Principal", esc(c.principal), true, esc(c.principal_role||""))}
      ${factHTML("Phone", phone)}
    </div>
    ${typeof c.match === "number" ? `<div class="match" title="Semantic retrieval similarity for this query">
      <span class="micro">Match</span><span class="bar"><i style="width:${Math.round(c.match*100)}%"></i></span>
      <span class="num">${c.match.toFixed(2)}</span></div>` : ""}
    <div class="vchips">
      ${(c.verification||[]).map(v=>`<span class="vchip">${esc(v)}</span>`).join("")}
      ${c.data_as_of ? `<span class="freshness num">as of ${esc(c.data_as_of)}</span>` : ""}
    </div>
    ${sigs ? `<div class="sig"><span class="micro">Recent activity</span>${sigs}</div>` : ""}
    ${c.classification_evidence ? `<details class="exp"><summary>Evidence &amp; classification</summary>
      <div class="body">Why this record qualifies as a family office:
        <span class="q">${esc(c.classification_evidence)}</span></div></details>` : ""}
    <div class="actions">
      <button class="act view-profile">↗ Full profile</button>
      <button class="act pin" aria-pressed="${pinned}">${pinned ? "★ Pinned" : "☆ Pin"}</button>
      <button class="act copy-cite">⧉ Copy citation</button>
    </div>
  </article>`;
}

function render(d){
  const r = $("#results");
  if(d.answered === false){
    const scopeDecline = (d.reason||"").startsWith("out-of-scope");
    const title = scopeDecline ? "Declined — outside the service's scope"
                               : "Declined — insufficient verified evidence";
    r.innerHTML = `<div class="reveal">
      <div class="verdict"><span class="title">${title}</span>${modeChip("abstain")}</div>
      <div class="answer abstain"><p>${esc(d.answer)}</p></div>
      <div class="abstain-help panel">
        <span class="micro">What this means</span>
        <ul class="md">
          <li>The dataset was searched, but nothing on file cleared the confidence bar this service
            requires before it will state a fact.</li>
          <li>Try naming a family-office type (single- or multi-family), a US state or country, an
            investing focus, or a specific firm name.</li>
          <li>Nothing was guessed or filled in to produce an answer — that is a deliberate limit, not
            an error.</li>
        </ul>
      </div></div>`;
    return;
  }
  const n = (d.citations||[]).length;
  let html = `<div class="reveal">
    <div class="verdict"><span class="title">Answered — grounded in ${n} verified record${n===1?"":"s"}</span>
      ${modeChip(d.mode)}</div>
    <div class="answer"><span class="micro">Executive summary</span>${answerHTML(d)}</div>`;

  if(d.cards && d.cards.length){
    html += `<div class="panel" style="padding: 16px; margin: 20px 0;">
        <span class="micro">Entity network — how the answer connects</span>
        <div id="vis-network" style="height: 220px; width: 100%;"></div>
      </div>`;

    html += `<div class="rec-head"><span class="micro">Verified records (${d.cards.length})</span>
      <button class="text-btn" id="export-cards">Export CSV</button></div>`;
    html += d.cards.map((c,i)=>card(c,i)).join("");
    html += `<div class="grounded">Retrieval: hybrid semantic + keyword over the verified dataset · citations: <span class="num">${(d.citations||[]).map(esc).join(", ")}</span></div>`;
  }
  html += `</div>`;
  r.innerHTML = html;

  if(d.cards && d.cards.length) vis.renderNetworkGraph("vis-network", d.cards);

  const exp = $("#export-cards");
  if(exp) exp.onclick = () => exportCSV(d.cards.map(c=>({name:c.name,type:c.type,location:c.location,
    aum:c.aum,principal:c.principal,phone:c.phone,website:c.website,confidence:c.confidence,
    verification:(c.verification||[]).join("; "),data_as_of:c.data_as_of})), "query-results.csv");
}

$("#results").addEventListener("click", e=>{
  const cardEl = e.target.closest(".card"); if(!cardEl) return;
  const id = cardEl.dataset.id;
  const name = cardEl.querySelector(".name").textContent.trim();
  if(e.target.closest(".pin")) togglePin(id, name, e.target.closest(".pin"));
  else if(e.target.closest(".view-profile")) openProfile(id);
  else if(e.target.closest(".copy-cite")){
    navigator.clipboard?.writeText(`${name} [${id}] — Family Office Intelligence, verified record`)
      .then(()=>toast("Citation copied")).catch(()=>toast("Copy failed"));
  }
});

/* ================= querying ================= */
const skeleton = `<div class="reveal">
  <div class="skel" style="height:20px;width:300px;margin-bottom:14px"></div>
  <div class="skel" style="height:96px;margin-bottom:14px;border-radius:12px"></div>
  <div class="skel" style="height:150px;margin-bottom:12px;border-radius:10px"></div>
  <div class="skel" style="height:150px;border-radius:10px"></div></div>`;
const LOADING_STAGES = ["Searching verified family-office intelligence…",
  "Checking supporting evidence…", "Preparing a grounded response…"];

async function ask(){
  const q = $("#q").value.trim(); if(!q) return;
  $("#ask").disabled = true;
  $("#results").innerHTML = `<div class="loading-stage reveal">${esc(LOADING_STAGES[0])}</div>` + skeleton;
  let stage = 0;
  const stageT = setInterval(()=>{
    stage = Math.min(stage+1, LOADING_STAGES.length-1);
    const el = $("#results .loading-stage");
    if(el) el.textContent = LOADING_STAGES[stage];
  }, 700);
  try{
    const res = await fetch("/query",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({query:q})});
    if(!res.ok) throw new Error("bad status");
    render(await res.json());
    pushRecent(q);
  }catch{
    $("#results").innerHTML = `<div class="answer abstain reveal">
      <p><strong>The service could not be reached.</strong> This is a connection problem, not a verdict on
      your question — please try again in a moment.</p></div>`;
  }finally{ clearInterval(stageT); $("#ask").disabled = false; }
}
$("#ask").onclick = ask;
$("#q").addEventListener("keydown", e=>{
  if(e.key==="Enter") ask();
  if(e.key==="Escape"){ $("#q").value=""; $("#q").blur(); }
});
document.addEventListener("keydown", e=>{
  if((e.metaKey||e.ctrlKey) && e.key.toLowerCase()==="k"){
    e.preventDefault(); showView("research"); $("#q").focus(); return;
  }
  if(e.key==="/" && !/input|select|textarea/i.test(document.activeElement.tagName)){
    e.preventDefault(); showView("research"); $("#q").focus();
  }
});

/* ================= directory / discover ================= */
let DIR = null, dirSort = {k:"name", asc:true};
const CONF_ORDER = {High:3, Medium:2, Low:1};
function aumVal(s){
  if(!s) return -1;
  const m = /\$\s*([\d.,]+)\s*(B|M|K|billion|million|thousand)?/i.exec(s);
  if(!m) return -1;
  const mult = {b:1e9, m:1e6, k:1e3, billion:1e9, million:1e6, thousand:1e3}[(m[2]||"").toLowerCase()] || 1;
  return parseFloat(m[1].replace(/,/g,"")) * mult;
}
function loadRecords(){
  if(DIR) return Promise.resolve(DIR);
  return fetch("/records").then(r=>r.json()).then(d=>{ DIR = d.records||[]; return DIR; });
}
async function loadDirectory(){
  $("#dir-body").innerHTML = `<tr><td colspan="7"><div class="skel" style="height:60px"></div></td></tr>`;
  let rows;
  try{ rows = await loadRecords(); }
  catch{ $("#dir-body").innerHTML = `<tr><td colspan="7">Could not load records.</td></tr>`; return; }
  renderDirectory();
  vis.renderGeoDistribution(rows);
  try{
    const s = await statsReady();
    vis.renderReachability(s);
    vis.renderEvidenceStrength(s);
    vis.renderConfidenceChart(s, "vis-confidence-donut-2");
    vis.renderCompletenessChart(s, "vis-completeness-bar-2");
  }catch{ /* panels stay empty rather than showing invented numbers */ }
}
function renderDirectory(){
  const f = ($("#dir-filter").value||"").toLowerCase();
  const t = $("#dir-type").value;
  const cf = $("#dir-conf").value;
  let rows = DIR.filter(r =>
    (!t || r.type===t) &&
    (!cf || r.confidence===cf) &&
    (!f || [r.name,r.location,r.principal,r.aum].some(x=>(x||"").toLowerCase().includes(f))));
  const {k,asc} = dirSort, dir = asc?1:-1;
  rows.sort((a,b)=>{
    if(k==="aum") return (aumVal(a.aum)-aumVal(b.aum))*dir;
    if(k==="confidence") return ((CONF_ORDER[a.confidence]||0)-(CONF_ORDER[b.confidence]||0))*dir;
    return String(a[k]||"").localeCompare(String(b[k]||""))*dir;
  });
  $("#dir-count").textContent = `${rows.length} of ${DIR.length}`;
  document.querySelectorAll("#dir-table th").forEach(th=>{
    if(!th.dataset.k) return;
    th.querySelector(".arrow").textContent = th.dataset.k===k ? (asc?"▲":"▼") : "";
  });
  $("#dir-body").innerHTML = rows.map(r=>`
    <tr data-id="${esc(r.fo_id)}" tabindex="0">
      <td><span class="nm">${esc(r.name)}</span></td>
      <td><span class="badge ${r.type==="Undetermined"?"b-und":"b-type"}">${esc(r.type)}</span></td>
      <td>${esc(r.location)||"—"}</td>
      <td class="num">${esc(r.aum)||"—"}</td>
      <td>${esc(r.principal)||"—"}</td>
      <td><span class="conf-dot" data-c="${esc(r.confidence)}">${esc(r.confidence)}</span></td>
      <td>${(r.verification||[]).slice(0,2).map(v=>`<span class="vchip">${esc(v)}</span>`).join(" ")}</td>
    </tr>`).join("");
}
$("#dir-filter").addEventListener("input", renderDirectory);
$("#dir-type").addEventListener("change", renderDirectory);
$("#dir-conf").addEventListener("change", renderDirectory);
$("#dir-reset").onclick = () => {
  $("#dir-filter").value=""; $("#dir-type").value=""; $("#dir-conf").value="";
  dirSort = {k:"name", asc:true}; renderDirectory();
};
document.querySelector("#dir-table thead").addEventListener("click", e=>{
  const th = e.target.closest("th"); if(!th || !th.dataset.k) return;
  const k = th.dataset.k;
  dirSort = {k, asc: dirSort.k===k ? !dirSort.asc : true};
  renderDirectory();
});
$("#dir-body").addEventListener("click", e=>{
  const tr = e.target.closest("tr[data-id]"); if(!tr) return;
  openProfile(tr.dataset.id);
});
$("#dir-body").addEventListener("keydown", e=>{
  if(e.key!=="Enter") return;
  const tr = e.target.closest("tr[data-id]"); if(!tr) return;
  openProfile(tr.dataset.id);
});
$("#dir-export").onclick = () => {
  if(!DIR) return;
  exportCSV(DIR.map(r=>({name:r.name,type:r.type,location:r.location,aum:r.aum,principal:r.principal,
    phone:r.phone,website:r.website,confidence:r.confidence,
    verification:(r.verification||[]).join("; "),data_as_of:r.data_as_of})), "family-office-directory.csv");
};

/* ================= FAMILY OFFICE PROFILE ================= */
const VERIFY_EXPLAIN = {
  "SEC 13F": "Verified against an SEC 13F/SC institutional-holdings filing.",
  "SEC ADV": "Verified against SEC investment-adviser registration (Form ADV).",
  "Website": "Verified against the firm's own published website.",
  "IRS 990-PF": "Verified against an IRS Form 990-PF nonprofit filing.",
  "Directory": "Verified against a curated reference directory.",
};
function confidenceExplain(conf){
  if(conf==="High") return "Multiple independent sources corroborate this record.";
  if(conf==="Medium") return "At least one authoritative source supports this record, without full independent corroboration.";
  return "Limited or single-source evidence — treat as a lead to verify, not a settled fact.";
}
async function renderProfile(id){
  showView("profile", {keepHash:true});
  const body = $("#profile-body");
  body.innerHTML = `<div class="skel" style="height:120px;border-radius:12px;margin-bottom:16px"></div>
    <div class="skel" style="height:220px;border-radius:12px"></div>`;
  let rows;
  try{ rows = await loadRecords(); } catch { body.innerHTML = `<div class="answer abstain"><p>Could not load records.</p></div>`; return; }
  const r = rows.find(x=>x.fo_id===id);
  if(!r){
    body.innerHTML = `<div class="answer abstain"><p><strong>Record not found.</strong> This firm is not in
      the currently served dataset — it may have been removed, or the id is invalid.</p></div>`;
    return;
  }
  const pinned = store.get("fo.pins", []).some(p=>p.id===r.fo_id);
  const notVerified = `<span class="nv">Not publicly verified</span>`;

  const decisionMakers = r.principal_name ? `
    <div class="dm-card">
      <div class="dm-name">${esc(r.principal_name)}</div>
      <div class="dm-title">${esc(r.principal_title||"Title not on file")} <span class="role">(${esc(r.principal_role||"role unconfirmed")})</span></div>
      <div class="facts" style="margin-top:10px">
        ${factHTML("Phone", r.principal_phone ? `<a href="tel:${esc(String(r.principal_phone).replace(/[^+\d]/g,""))}" class="num">${esc(r.principal_phone)}</a>` : notVerified)}
        ${factHTML("Email", r.principal_email ? `<a href="mailto:${esc(r.principal_email)}">${esc(r.principal_email)}</a>${r.principal_email_status?` <span class="role">(${esc(r.principal_email_status)})</span>`:""}` : notVerified)}
        ${factHTML("LinkedIn", r.principal_linkedin ? `<a href="${esc(r.principal_linkedin)}" target="_blank" rel="noopener">Profile</a>` : notVerified)}
      </div>
    </div>` : `<div class="empty-state">No named decision-maker was identified in the available public
      sources for this firm.</div>`;

  const firmInbox = r.firm_contact_email ? `<div class="panel-note" style="margin-top:10px">
      Firm-level inbox on file (not a route to a named person): <a href="mailto:${esc(r.firm_contact_email)}">${esc(r.firm_contact_email)}</a>
      ${r.firm_contact_email_status?` — ${esc(r.firm_contact_email_status)}`:""}</div>` : "";

  const signals = (r.signals||[]);
  const activity = signals.length ? `<div class="timeline">${signals.map(s=>`
      <div class="tl-row">
        <span class="tl-date num">${esc(s.date||"undated")}</span>
        <span class="tl-body">${esc(s.text)}${s.source?` <span class="role">— ${esc(s.source)}</span>`:""}</span>
      </div>`).join("")}</div>`
    : `<div class="empty-state">No dated recent activity is on file for this firm.</div>`;

  const cnv = (r.could_not_verify||[]);
  const evidenceDetail = (r.verification_detail && r.verification_detail.length) ? r.verification_detail.map(v=>`
      <div class="ev-row">
        <div class="ev-head"><span class="ev-source">${esc(v.source)}</span><span class="ev-date num">${esc(v.accessed_at)}</span></div>
        <div class="ev-verifies">${esc(v.verifies)}</div>
        ${VERIFY_EXPLAIN[v.source] ? `<div class="panel-note" style="margin:4px 0 0">${VERIFY_EXPLAIN[v.source]}</div>`:""}
        ${v.url ? `<a class="ev-link" href="${esc(v.url)}" target="_blank" rel="noopener">View source ↗</a>`:""}
      </div>`).join("") : `<div class="empty-state">No individual source records on file for this firm.</div>`;

  body.innerHTML = `
    <header class="profile-head">
      <div class="profile-head-top">
        <h1 class="profile-name">${esc(r.name)}</h1>
        <div class="profile-actions">
          <button class="act pin" aria-pressed="${pinned}" id="profile-pin">${pinned?"★ Pinned":"☆ Pin"}</button>
          <button class="act copy-cite" id="profile-copy">⧉ Copy citation</button>
        </div>
      </div>
      <div class="profile-meta">
        <span class="badge ${r.type==="Undetermined"?"b-und":"b-type"}">${esc(r.type)}</span>
        <span class="badge b-${esc(r.confidence)}" title="${esc(confidenceExplain(r.confidence))}">${esc(r.confidence)} confidence</span>
        ${r.location?`<span class="pm-item">${esc(r.location)}</span>`:""}
        ${r.website?`<a class="pm-item" href="${esc(r.website)}" target="_blank" rel="noopener">${esc(r.website).replace(/^https?:\/\/(www\.)?/,"")} ↗</a>`:""}
      </div>
      <p class="confidence-explain">${esc(confidenceExplain(r.confidence))}</p>
    </header>

    <div class="profile-grid">
      <div class="profile-col">
        <section class="profile-section">
          <h2 class="section-h">Overview</h2>
          <div class="facts facts-wide">
            ${factHTML("Background", r.description ? esc(r.description) : "")}
            ${factHTML("Investment thesis", r.investment_thesis ? esc(r.investment_thesis) : "")}
            ${factHTML("Investing sectors", (r.investing_sectors||[]).length ? esc(r.investing_sectors.join(", ")) : "")}
            ${factHTML("Estimated AUM", esc(r.aum))}
            ${factHTML("Headquarters", esc([r.city,r.state,r.country].filter(Boolean).join(", ")))}
            ${factHTML("Phone", r.phone ? `<a href="tel:${esc(String(r.phone).replace(/[^+\d]/g,""))}" class="num">${esc(r.phone)}</a>` : "")}
            ${factHTML("Corporate LinkedIn", r.corporate_linkedin ? `<a href="${esc(r.corporate_linkedin)}" target="_blank" rel="noopener">Profile</a>` : "")}
          </div>
          ${!r.description && !r.investment_thesis ? `<div class="empty-state">No background or investment
            thesis is on file for this firm beyond its classification evidence below.</div>` : ""}
        </section>

        <section class="profile-section">
          <h2 class="section-h">Decision makers</h2>
          ${decisionMakers}${firmInbox}
        </section>

        <section class="profile-section">
          <h2 class="section-h">Recent signals</h2>
          ${activity}
        </section>
      </div>

      <div class="profile-col">
        <section class="profile-section">
          <h2 class="section-h">Evidence</h2>
          <p class="panel-note">Why this product believes what it shows about this firm.</p>
          <div class="ev-block">
            <span class="micro">Classification evidence</span>
            <p class="ev-classification">${r.evidence?esc(r.evidence):"No classification evidence on file."}</p>
          </div>
          <div class="ev-block">
            <span class="micro">Discovered via</span>
            <p>${esc(r.discovery_source||"Not on file")}</p>
          </div>
          <div class="ev-block">
            <span class="micro">Verified via (${(r.verification_detail||[]).length} source${(r.verification_detail||[]).length===1?"":"s"})</span>
            ${evidenceDetail}
          </div>
          ${cnv.length ? `<div class="ev-block">
            <span class="micro">Could not verify</span>
            <p class="panel-note" style="margin:2px 0 0">${cnv.map(esc).join(", ")} — left blank rather than
              guessed.</p></div>` : ""}
          <div class="ev-block">
            <span class="micro">Data as of</span>
            <p class="num">${esc(r.data_as_of)}</p>
          </div>
        </section>
      </div>
    </div>
  `;
  $("#profile-pin").onclick = (e) => togglePin(r.fo_id, r.name, e.currentTarget);
  $("#profile-copy").onclick = () => {
    navigator.clipboard?.writeText(`${r.name} [${r.fo_id}] — Family Office Intelligence, verified record`)
      .then(()=>toast("Citation copied")).catch(()=>toast("Copy failed"));
  };
}

/* ================= CSV export (client-side, current data only) ================= */
function exportCSV(rows, filename){
  if(!rows || !rows.length){ toast("Nothing to export"); return; }
  const cols = Object.keys(rows[0]);
  const cell = v => `"${String(v??"").replace(/"/g,'""')}"`;
  const csv = [cols.join(","), ...rows.map(r=>cols.map(c=>cell(r[c])).join(","))].join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], {type:"text/csv"}));
  a.download = filename; a.click(); URL.revokeObjectURL(a.href);
  toast("Exported " + rows.length + " rows");
}
/* ================= AGENT — multi-step goal execution ================= */
const GOAL_EXAMPLES = [
  "Identify the 10 family offices in the dataset that are the strongest prospects for a private-markets fund seeking new limited partners, rank them by overall fit, and identify the relevant named decision-maker and contact route for each.",
  "Identify the family offices in the dataset that are the best fit for a lower-middle-market healthcare services fund seeking limited partners, and tell me how confident you are in each.",
];
$("#goal-chips").innerHTML = GOAL_EXAMPLES.map(e=>`<button class="chip">${esc(e.slice(0,70))}…</button>`).join("");
$("#goal-chips").addEventListener("click", e=>{
  const b = e.target.closest("button.chip"); if(!b) return;
  const idx = [...e.currentTarget.children].indexOf(b);
  $("#goal-input").value = GOAL_EXAMPLES[idx]; runGoal();
});

const UNCERTAINTY_LABEL = {
  sufficient: {label: "Strong evidence", cls: "hi"},
  thin: {label: "Thin evidence — treat as a lead, not a conclusion", cls: "lo"},
  stale: {label: "Evidence is out of date", cls: "lo"},
  insufficient: {label: "Not enough evidence to assess", cls: "lo"},
};

function goalCard(item){
  const u = UNCERTAINTY_LABEL[item.uncertainty] || {label: item.uncertainty, cls: "lo"};
  const contact = item.contact_route
    ? `<div class="g-contact">Contact: <b>${esc(item.contact_route.kind.replace(/_/g," "))}</b> — ${esc(item.contact_route.value)}
        <span class="g-ev">(${esc(item.contact_route.evidence)})</span></div>`
    : `<div class="g-contact g-nocontact">No verified route to a named decision-maker on file.</div>`;
  const dm = item.decision_maker ? `<div class="g-dm">Decision-maker: ${esc(item.decision_maker)}</div>` : "";
  return `<div class="panel g-card">
    <div class="g-head"><span class="g-rank">#${item.rank}</span>
      <span class="g-name">${esc(item.family_office_name)}</span>
      <span class="g-badge ${u.cls}">${esc(u.label)}</span></div>
    <div class="g-why">${esc(item.fit_reasoning)}</div>
    ${dm}${contact}
    <div class="g-evidence">Evidence on file: ${item.evidence.n_verification_sources} independent source(s),
      record confidence ${esc(item.evidence.record_confidence)}.
      ${item.uncertainty_reason ? esc(item.uncertainty_reason) + "." : ""}</div>
    <div class="g-action">Next step: ${esc(item.recommended_action)}</div>
  </div>`;
}

function renderGoalResult(result){
  const c = result.counts;
  const summary = `<div class="panel" style="margin-bottom:16px;">
    <p style="margin:0 0 8px;"><b>What the agent did:</b> read your goal, checked it against
    ${c.considered} candidate records, and found ${c.sufficient_evidence} with strong supporting evidence,
    ${c.thin_or_stale_evidence} with thin or dated evidence, and ${c.insufficient_evidence} without enough
    evidence to assess. It ran in ${result.elapsed_seconds}s.</p>
    <details><summary style="cursor:pointer;">What a single search would have returned instead</summary>
      <p style="white-space:pre-wrap;margin-top:8px;">${esc(result.manual_retrieval_baseline.answer)}</p>
    </details>
  </div>`;
  const cards = result.structured_output.map(goalCard).join("");
  $("#goal-results").innerHTML = summary + cards;
}

let GOAL_POLL = null;
function pollGoal(runId){
  clearInterval(GOAL_POLL);
  GOAL_POLL = setInterval(async () => {
    const r = await fetch(`/goal/${runId}`); const d = await r.json();
    if(d.status === "running"){
      $("#goal-status").innerHTML = `<div class="panel">Working — decomposing the goal, retrieving and
        comparing candidates, checking evidence… this can take several minutes.</div>`;
    } else if(d.status === "done"){
      clearInterval(GOAL_POLL);
      $("#goal-status").innerHTML = "";
      renderGoalResult(d.result);
    } else if(d.status === "failed"){
      clearInterval(GOAL_POLL);
      $("#goal-status").innerHTML = `<div class="panel">The agent could not complete this run: ${esc(d.error||"unknown error")}</div>`;
    }
  }, 4000);
}

async function runGoal(){
  const text = $("#goal-input").value.trim();
  if(!text) return;
  $("#goal-results").innerHTML = "";
  $("#goal-status").innerHTML = `<div class="panel">Starting — the agent is reading your goal…</div>`;
  const r = await fetch("/goal", {method:"POST", headers:{"Content-Type":"application/json"},
    body: JSON.stringify({goal: text})});
  const d = await r.json();
  if(d.run_id) pollGoal(d.run_id);
  else $("#goal-status").innerHTML = `<div class="panel">${esc(d.error||"Could not start the agent.")}</div>`;
}
$("#goal-run").onclick = runGoal;
$("#goal-input").addEventListener("keydown", e=>{ if(e.key==="Enter") runGoal(); });

/* ================= initial route ================= */
if(location.hash){ routeFromHash(); } else { showView("home", {keepHash:true}); }
