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

/* ================= theme ================= */
const themeBtn = $("#theme");
const savedTheme = store.get("fo.theme", null);
if(savedTheme) document.documentElement.dataset.theme = savedTheme;
themeBtn.onclick = () => {
  const cur = document.documentElement.dataset.theme ||
    (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next; store.set("fo.theme", next);
};

/* ================= tabs ================= */
const views = { research: [$("#tab-research"), $("#view-research")],
                agent: [$("#tab-agent"), $("#view-agent")],
                directory: [$("#tab-directory"), $("#view-directory")] };
function showView(name){
  for(const [k,[tab,view]] of Object.entries(views)){
    const on = k===name;
    tab.setAttribute("aria-selected", on);
    view.classList.toggle("hide", !on);
  }
  if(name==="directory") loadDirectory();
}
views.research[0].onclick = () => showView("research");
views.agent[0].onclick = () => showView("agent");
views.directory[0].onclick = () => showView("directory");

import * as vis from "./visualizations.js";

/* ================= status + coverage (real, live-computed) ================= */
fetch("/health").then(r=>r.json()).then(d=>{
  $("#status-text").textContent = `${d.records} verified records`;
}).catch(()=>{ $("#status-text").textContent = "offline"; });

fetch("/stats").then(r=>r.json()).then(s=>{
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
    
  vis.renderCompletenessChart(s);
  vis.renderConfidenceChart(s);
}).catch(()=>{ $("#coverage").innerHTML = `<div class="empty">Unavailable.</div>`; });

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
}
$("#recent").addEventListener("click", e=>{
  const b = e.target.closest("button[data-q]"); if(!b) return;
  $("#q").value = b.dataset.q; showView("research"); ask();
});
$("#clear-recent").onclick = () => { store.set("fo.recent", []); renderRecent(); };

function renderPins(){
  const ps = store.get("fo.pins", []);
  $("#pins").innerHTML = ps.length
    ? ps.map(p=>`<li><button data-q="Tell me about ${esc(p.name)}" title="Research ${esc(p.name)}">★ ${esc(p.name)}</button></li>`).join("")
    : `<li class="empty">Pin records from results.</li>`;
}
$("#pins").addEventListener("click", e=>{
  const b = e.target.closest("button[data-q]"); if(!b) return;
  $("#q").value = b.dataset.q; showView("research"); ask();
});
function togglePin(id, name, btn){
  let ps = store.get("fo.pins", []);
  const has = ps.some(p=>p.id===id);
  ps = has ? ps.filter(p=>p.id!==id) : [...ps, {id, name}];
  store.set("fo.pins", ps); renderPins();
  btn.setAttribute("aria-pressed", !has);
  btn.innerHTML = !has ? "★ Pinned" : "☆ Pin";
  toast(!has ? "Pinned" : "Unpinned");
}
renderRecent(); renderPins();

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
  abstain: ["abst","Declined","The retrieved evidence did not clear the grounding threshold, so the system declines rather than guessing."]
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

function card(c, i){
  const conf = c.confidence || "Low";
  const typeCls = c.type === "Undetermined" ? "b-und" : "b-type";
  const nm = c.website
    ? `<a href="${esc(c.website)}" target="_blank" rel="noopener">${esc(c.name)}</a>` : esc(c.name);
  const phone = c.phone
    ? `<a href="tel:${esc(String(c.phone).replace(/[^+\d]/g,""))}" class="num">${esc(c.phone)}</a>` : "";
  const sigs = (c.signals||[]).slice(0,3).map(s=>`<div class="sig-row">${esc(s)}</div>`).join("");
  const pinned = store.get("fo.pins", []).some(p=>p.id===c.fo_id);
  return `<article class="card reveal" style="animation-delay:${Math.min(i*45,270)}ms" data-id="${esc(c.fo_id)}">
    <div class="head">
      <span class="name">${nm}</span>
      <span class="badges">
        <span class="badge ${typeCls}">${esc(c.type)}</span>
        <span class="badge b-${esc(conf)}" title="Overall record confidence — the weakest link across identity anchors">${esc(conf)} confidence</span>
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
    ${sigs ? `<div class="sig"><span class="micro">Recent activity — SEC 13F</span>${sigs}</div>` : ""}
    ${c.classification_evidence ? `<details class="exp"><summary>Evidence &amp; classification</summary>
      <div class="body">Why this record qualifies as a family office:
        <span class="q">${esc(c.classification_evidence)}</span></div></details>` : ""}
    <div class="actions">
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
      <div class="answer abstain"><p>${esc(d.answer)}</p></div></div>`;
    return;
  }
  const n = (d.citations||[]).length;
  let html = `<div class="reveal">
    <div class="verdict"><span class="title">Answered — grounded in ${n} verified record${n===1?"":"s"}</span>
      ${modeChip(d.mode)}</div>
    <div class="answer"><span class="micro">Executive summary</span>${answerHTML(d)}</div>`;
    
  html += vis.generateTimelineHtml(d);
  
  if(d.cards && d.cards.length){
    html += `<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0;">
      <div class="panel" style="padding: 16px;">
        <span class="micro">Evidence Verification Funnel</span>
        <div id="vis-funnel" style="height: 120px; width: 100%;"></div>
      </div>
      <div class="panel" style="padding: 16px;">
        <span class="micro">Entity Network</span>
        <div id="vis-network" style="height: 220px; width: 100%;"></div>
      </div>
    </div>`;
      
    html += `<div class="rec-head"><span class="micro">Verified records (${d.cards.length})</span>
      <button class="text-btn" id="export-cards">Export CSV</button></div>`;
    html += d.cards.map((c,i)=>card(c,i)).join("");
    html += `<div class="grounded">Retrieval: hybrid semantic + keyword over the verified dataset · citations: <span class="num">${(d.citations||[]).map(esc).join(", ")}</span></div>`;
  }
  html += `</div>`;
  r.innerHTML = html;
  
  if(d.cards && d.cards.length) {
    // We assume total corpus size ~500 for demo, this would normally come from the backend response
    vis.renderVerificationFunnel("vis-funnel", 500, d.cards.length);
    vis.renderNetworkGraph("vis-network", d.cards);
  }
  
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

async function ask(){
  const q = $("#q").value.trim(); if(!q) return;
  $("#ask").disabled = true;
  $("#results").innerHTML = skeleton;
  try{
    const res = await fetch("/query",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({query:q})});
    render(await res.json());
    pushRecent(q);
  }catch{
    $("#results").innerHTML = `<div class="answer abstain reveal"><p>The service could not be reached. Please try again.</p></div>`;
  }finally{ $("#ask").disabled = false; }
}
$("#ask").onclick = ask;
$("#q").addEventListener("keydown", e=>{
  if(e.key==="Enter") ask();
  if(e.key==="Escape"){ $("#q").value=""; $("#q").blur(); }
});
document.addEventListener("keydown", e=>{
  if(e.key==="/" && !/input|select|textarea/i.test(document.activeElement.tagName)){
    e.preventDefault(); showView("research"); $("#q").focus();
  }
});

/* ================= directory ================= */
let DIR = null, dirSort = {k:"name", asc:true};
const CONF_ORDER = {High:3, Medium:2, Low:1};
function aumVal(s){
  if(!s) return -1;
  const m = /\$\s*([\d.,]+)\s*(B|M|K|billion|million|thousand)?/i.exec(s);
  if(!m) return -1;
  const mult = {b:1e9, m:1e6, k:1e3, billion:1e9, million:1e6, thousand:1e3}[(m[2]||"").toLowerCase()] || 1;
  return parseFloat(m[1].replace(/,/g,"")) * mult;
}
async function loadDirectory(){
  if(DIR){ renderDirectory(); return; }
  $("#dir-body").innerHTML = `<tr><td colspan="5"><div class="skel" style="height:60px"></div></td></tr>`;
  try{
    DIR = (await (await fetch("/records")).json()).records || [];
  }catch{ $("#dir-body").innerHTML = `<tr><td colspan="5">Could not load records.</td></tr>`; return; }
  renderDirectory();
  vis.renderWorldMap(DIR);
  vis.renderOperatingCycle();
  vis.renderEmployeeStatus();
}
function renderDirectory(){
  const f = ($("#dir-filter").value||"").toLowerCase();
  const t = $("#dir-type").value;
  let rows = DIR.filter(r =>
    (!t || r.type===t) &&
    (!f || [r.name,r.location,r.principal,r.aum].some(x=>(x||"").toLowerCase().includes(f))));
  const {k,asc} = dirSort, dir = asc?1:-1;
  rows.sort((a,b)=>{
    if(k==="aum") return (aumVal(a.aum)-aumVal(b.aum))*dir;
    if(k==="confidence") return ((CONF_ORDER[a.confidence]||0)-(CONF_ORDER[b.confidence]||0))*dir;
    return String(a[k]||"").localeCompare(String(b[k]||""))*dir;
  });
  $("#dir-count").textContent = `${rows.length} of ${DIR.length}`;
  document.querySelectorAll("#dir-table th").forEach(th=>{
    th.querySelector(".arrow").textContent = th.dataset.k===k ? (asc?"▲":"▼") : "";
  });
  $("#dir-body").innerHTML = rows.map(r=>`
    <tr data-id="${esc(r.fo_id)}" tabindex="0">
      <td><span class="nm">${esc(r.name)}</span></td>
      <td><span class="badge ${r.type==="Undetermined"?"b-und":"b-type"}">${esc(r.type)}</span></td>
      <td>${esc(r.location)||"—"}</td>
      <td class="num">${esc(r.aum)||"—"}</td>
      <td><span class="badge b-${esc(r.confidence)}">${esc(r.confidence)}</span></td>
    </tr>`).join("");
}
$("#dir-filter").addEventListener("input", renderDirectory);
$("#dir-type").addEventListener("change", renderDirectory);
document.querySelector("#dir-table thead").addEventListener("click", e=>{
  const th = e.target.closest("th"); if(!th) return;
  const k = th.dataset.k;
  dirSort = {k, asc: dirSort.k===k ? !dirSort.asc : true};
  renderDirectory();
});
$("#dir-body").addEventListener("click", e=>{
  const tr = e.target.closest("tr[data-id]"); if(!tr) return;
  const existing = tr.nextElementSibling;
  document.querySelectorAll("tr.detail").forEach(x=>x.remove());
  if(existing && existing.classList.contains("detail")) return;   // toggle closed
  const r = DIR.find(x=>x.fo_id===tr.dataset.id); if(!r) return;
  const d = document.createElement("tr"); d.className = "detail reveal";
  d.innerHTML = `<td colspan="5">
    <div class="facts">
      ${factHTML("Principal", esc(r.principal), false, esc(r.principal_role||""))}
      ${factHTML("Phone", esc(r.phone), true)}
      ${factHTML("Website", r.website?`<a href="${esc(r.website)}" target="_blank" rel="noopener">${esc(r.website).replace(/^https?:\/\/(www\.)?/,"")}</a>`:"")}
      ${factHTML("Data as of", esc(r.data_as_of), true)}
    </div>
    <div class="vchips">${(r.verification||[]).map(v=>`<span class="vchip">${esc(v)}</span>`).join("")}</div>
    ${(r.signals||[]).length?`<div class="sig"><span class="micro">Recent activity — SEC 13F</span>
      ${r.signals.slice(0,3).map(s=>`<div class="sig-row">${esc(s)}</div>`).join("")}</div>`:""}
    ${r.evidence?`<details class="exp"><summary>Evidence &amp; classification</summary>
      <div class="body"><span class="q">${esc(r.evidence)}</span></div></details>`:""}
  </td>`;
  tr.after(d);
});
$("#dir-export").onclick = () => {
  if(!DIR) return;
  exportCSV(DIR.map(r=>({name:r.name,type:r.type,location:r.location,aum:r.aum,principal:r.principal,
    phone:r.phone,website:r.website,confidence:r.confidence,
    verification:(r.verification||[]).join("; "),data_as_of:r.data_as_of})), "family-office-directory.csv");
};

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
