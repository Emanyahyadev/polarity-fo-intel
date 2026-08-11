import * as d3 from "d3";

// 0a. Hero globe — a real, slowly-rotating orthographic projection of actual
// world geography (public world-atlas topology), with dots placed at country
// CENTROIDS COMPUTED FROM THAT SAME GEOMETRY (not a hand-picked lat/lon guess)
// for every country that actually has verified firms on file (GET /records ->
// hq_country). Dot size is the real count for that country. Nothing here is
// fabricated: the landmasses are real, the centroids are computed from them,
// and the counts are the served records. Purely decorative fallback (a static
// radial motif) if the world-atlas geometry can't be fetched — never fake data
// standing in for the globe.
export async function renderGlobe(containerId, records) {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.innerHTML = "";
    const size = Math.min(el.clientWidth || 460, el.clientHeight || 460) || 460;
    const width = el.clientWidth || size, height = el.clientHeight || size;

    const counts = new Map();
    for (const r of records) {
        const c = (r.country || "").trim();
        if (c) counts.set(c, (counts.get(c) || 0) + 1);
    }

    const svg = d3.select(el).append("svg")
        .attr("viewBox", [0, 0, width, height])
        .attr("width", "100%").attr("height", "100%")
        .style("display", "block");

    let land, countries;
    try {
        const world = await d3.json("https://unpkg.com/world-atlas@2/countries-110m.json");
        const topojson = await import("https://cdn.jsdelivr.net/npm/topojson-client@3/+esm");
        countries = topojson.feature(world, world.objects.countries).features;
        land = topojson.feature(world, world.objects.land);
    } catch (e) {
        // Fallback: an abstract, explicitly non-factual orbital motif — no data implied.
        const r = Math.min(width, height) / 2 - 10;
        const g = svg.append("g").attr("transform", `translate(${width/2},${height/2})`);
        g.append("circle").attr("r", r).attr("fill", "var(--accent-tint)").attr("stroke", "var(--accent-line)");
        for (let i = 1; i <= 3; i++)
            g.append("circle").attr("r", r * (0.4 + i*0.18)).attr("fill", "none")
                .attr("stroke", "var(--line2)").attr("stroke-dasharray", "2,4");
        return;
    }

    const R = Math.min(width, height) / 2 - 14;
    const projection = d3.geoOrthographic().scale(R).translate([width/2, height/2])
        .rotate([10, -18]).clipAngle(90);
    const path = d3.geoPath(projection);

    svg.append("circle").attr("cx", width/2).attr("cy", height/2).attr("r", R)
        .attr("fill", "var(--surface)").attr("stroke", "var(--line2)").attr("stroke-width", 1);

    const graticule = d3.geoGraticule10();
    svg.append("path").datum(graticule).attr("d", path)
        .attr("fill", "none").attr("stroke", "var(--line)").attr("stroke-width", 0.5);

    const landPath = svg.append("path").datum(land).attr("d", path)
        .attr("fill", "var(--accent-tint)").attr("stroke", "var(--accent-line)").attr("stroke-width", 0.6);

    // Match real record countries to the atlas geometry by name, then take the
    // GEOMETRIC centroid of the matched feature — no invented coordinates.
    const norm = s => s.toLowerCase().replace(/[^a-z]/g, "");
    const nodes = [];
    for (const [name, count] of counts) {
        const n = norm(name);
        const feat = countries.find(f => {
            const fn = norm(f.properties?.name || "");
            return fn === n || fn.includes(n) || n.includes(fn);
        });
        if (!feat) continue;
        const centroid = d3.geoCentroid(feat);
        nodes.push({ name, count, lon: centroid[0], lat: centroid[1] });
    }
    nodes.sort((a,b) => b.count - a.count);
    const top = nodes.slice(0, 4);
    const maxCount = d3.max(nodes, d => d.count) || 1;
    const rScale = d3.scaleSqrt().domain([1, maxCount]).range([2.5, 8]);

    const dotsG = svg.append("g");
    const labelsG = svg.append("g");

    function visible([lon, lat]) {
        const rot = projection.rotate();
        const center = [-rot[0], -rot[1]];
        const dist = d3.geoDistance([lon, lat], center);
        return dist < Math.PI / 2;
    }

    function redraw() {
        landPath.attr("d", path);
        svg.select("path.grat").remove();
        dotsG.selectAll("circle").data(nodes).join("circle")
            .attr("transform", d => { const p = projection([d.lon, d.lat]); return p ? `translate(${p[0]},${p[1]})` : null; })
            .attr("r", d => rScale(d.count))
            .attr("fill", "var(--accent)")
            .attr("opacity", d => visible([d.lon, d.lat]) ? 0.85 : 0)
            .attr("stroke", "var(--surface)").attr("stroke-width", 1);
        labelsG.selectAll("text").data(top).join("text")
            .attr("transform", d => { const p = projection([d.lon, d.lat]); return p ? `translate(${p[0]},${p[1]-12})` : null; })
            .attr("text-anchor", "middle").attr("font-size", 10.5).attr("font-weight", 600)
            .attr("fill", "var(--ink2)")
            .attr("opacity", d => visible([d.lon, d.lat]) ? 1 : 0)
            .text(d => d.name);
    }
    redraw();

    if (!matchMedia("(prefers-reduced-motion: reduce)").matches) {
        d3.timer(elapsed => {
            projection.rotate([10 + elapsed * 0.006, -18]);
            redraw();
        });
    }
}

// 0. Hero intelligence network — a DECORATIVE ambient visual built from a real
// sample of records (GET /records): a central hub, spoke nodes for each firm
// TYPE actually present in the sample, and leaf nodes for real firm names. The
// only relationship drawn is "this firm has this type", which is true of every
// record shown — nothing is invented, and the caption under the visual says
// plainly that this is a sample, not the full dataset or a factual network.
export function renderIntelligenceNetwork(containerId, records) {
    const el = document.getElementById(containerId);
    if (!el || !records || !records.length) return;
    el.innerHTML = "";
    const width = el.clientWidth || 480, height = el.clientHeight || 420;

    const svg = d3.select(el).append("svg")
        .attr("viewBox", [0, 0, width, height])
        .attr("width", "100%").attr("height", "100%")
        .style("display", "block");

    const sample = [...records].sort(() => Math.random() - 0.5).slice(0, 22);
    const byType = new Map();
    for (const r of sample) {
        const t = r.type || "Undetermined";
        if (!byType.has(t)) byType.set(t, []);
        byType.get(t).push(r);
    }
    const color = { "Single-Family Office": "var(--accent)", "Multi-Family Office": "#1D5DAD",
                     "Undetermined": "var(--ink3)" };

    const nodes = [{ id: "__hub", label: "Family Offices", r: 9, group: "hub" }];
    const links = [];
    for (const [type, firms] of byType) {
        const typeId = "__type_" + type;
        nodes.push({ id: typeId, label: type, r: 5, group: "type", color: color[type] || "var(--ink3)" });
        links.push({ source: "__hub", target: typeId });
        for (const f of firms) {
            nodes.push({ id: f.fo_id, label: f.name, r: 3, group: "firm", color: color[type] || "var(--ink3)" });
            links.push({ source: typeId, target: f.fo_id });
        }
    }

    const sim = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(links).id(d => d.id).distance(d =>
            d.target.group === "firm" ? 46 : 90).strength(0.7))
        .force("charge", d3.forceManyBody().strength(-70))
        .force("center", d3.forceCenter(width / 2, height / 2))
        .force("collide", d3.forceCollide(d => d.r + 14));

    const link = svg.append("g").selectAll("line").data(links).join("line")
        .attr("stroke", "var(--line2)").attr("stroke-width", 1);

    const node = svg.append("g").selectAll("circle").data(nodes).join("circle")
        .attr("r", d => d.r)
        .attr("fill", d => d.group === "hub" ? "var(--ink)" : (d.color || "var(--ink3)"))
        .attr("opacity", d => d.group === "firm" ? 0.85 : 1);

    const label = svg.append("g").selectAll("text")
        .data(nodes.filter(d => d.group !== "firm"))
        .join("text")
        .text(d => d.label)
        .attr("font-size", d => d.group === "hub" ? 12 : 10.5)
        .attr("font-weight", d => d.group === "hub" ? 700 : 600)
        .attr("fill", "var(--ink2)")
        .attr("text-anchor", "middle")
        .attr("dy", d => -(d.r + 8));

    node.append("title").text(d => d.label);

    sim.on("tick", () => {
        for (const n of nodes) {
            n.x = Math.max(16, Math.min(width - 16, n.x));
            n.y = Math.max(16, Math.min(height - 16, n.y));
        }
        link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
        node.attr("cx", d => d.x).attr("cy", d => d.y);
        label.attr("x", d => d.x).attr("y", d => d.y);
    });
    // gentle continuous drift so the visual reads as "alive" without being distracting
    sim.alphaTarget(0.02).alphaDecay(0.02);
    setTimeout(() => sim.alphaTarget(0), 4000);
}

// Ensure charts are responsive
function responsiveSvg(containerId, height) {
    const container = document.getElementById(containerId);
    if (!container) return null;
    container.innerHTML = "";
    const width = container.clientWidth || 300;
    const svg = d3.select(container).append("svg")
        .attr("viewBox", [0, 0, width, height])
        .attr("width", "100%")
        .attr("height", "100%")
        .style("max-width", "100%")
        .style("height", "auto")
        .style("display", "block");
    return { svg, width, height };
}

// 1. Dataset Completeness (Bar Chart)
export function renderCompletenessChart(stats, containerId = "vis-completeness-bar") {
    if (!stats || !stats.coverage) return;
    const res = responsiveSvg(containerId, 120);
    if (!res) return;
    const { svg, width, height } = res;
    
    const margin = {top: 10, right: 30, bottom: 20, left: 80};
    const innerWidth = width - margin.left - margin.right;
    const innerHeight = height - margin.top - margin.bottom;
    
    const data = [
        {name: "AUM", value: stats.coverage.aum || 0},
        {name: "Principal", value: stats.coverage.principal || 0},
        {name: "Website", value: stats.coverage.website || 0},
        {name: "Signals", value: stats.coverage.signals || 0}
    ];
    
    const maxVal = stats.records || 500;
    const x = d3.scaleLinear().domain([0, maxVal]).range([0, innerWidth]);
    const y = d3.scaleBand().domain(data.map(d=>d.name)).range([0, innerHeight]).padding(0.3);
    
    const g = svg.append("g").attr("transform", `translate(${margin.left},${margin.top})`);
    
    // Background tracks
    g.selectAll(".track")
        .data(data)
        .join("rect")
        .attr("class", "track")
        .attr("x", 0)
        .attr("y", d => y(d.name))
        .attr("height", y.bandwidth())
        .attr("width", innerWidth)
        .attr("fill", "var(--line)")
        .attr("rx", 4);
        
    // Foreground bars (animated)
    g.selectAll(".bar")
        .data(data)
        .join("rect")
        .attr("class", "bar")
        .attr("x", 0)
        .attr("y", d => y(d.name))
        .attr("height", y.bandwidth())
        .attr("width", 0)
        .attr("fill", "var(--accent)")
        .attr("rx", 4)
        .transition().duration(800).ease(d3.easeCubicOut)
        .attr("width", d => x(d.value));
        
    // Labels
    g.append("g")
        .call(d3.axisLeft(y).tickSize(0))
        .call(g => g.select(".domain").remove())
        .call(g => g.selectAll("text").attr("fill", "var(--ink2)").style("font-family", "var(--font)").style("font-size", "12px"));
        
    g.selectAll(".label")
        .data(data)
        .join("text")
        .attr("x", d => x(d.value) + 5)
        .attr("y", d => y(d.name) + y.bandwidth()/2 + 4)
        .text(d => d.value)
        .style("font-family", "var(--mono)")
        .style("font-size", "11px")
        .style("fill", "var(--ink3)")
        .attr("opacity", 0)
        .transition().delay(800)
        .attr("opacity", 1);
}

// 2. Confidence Distribution (Donut Chart)
export function renderConfidenceChart(stats, containerId = "vis-confidence-donut") {
    if (!stats || !stats.confidence) return;
    const res = responsiveSvg(containerId, 120);
    if (!res) return;
    const { svg, width, height } = res;
    
    const data = [
        {name: "High", value: stats.confidence["High"] || 0, color: "var(--ok)"},
        {name: "Medium", value: stats.confidence["Medium"] || 0, color: "var(--warn)"},
        {name: "Low", value: stats.confidence["Low"] || 0, color: "var(--neutral-badge)"}
    ].filter(d => d.value > 0);
    
    const radius = Math.min(width, height) / 2 - 5;
    const g = svg.append("g").attr("transform", `translate(${width/2},${height/2})`);
    
    const pie = d3.pie().value(d => d.value).sort(null);
    const arc = d3.arc().innerRadius(radius * 0.6).outerRadius(radius);
    
    const arcs = g.selectAll("path")
        .data(pie(data))
        .join("path")
        .attr("fill", d => d.data.color)
        .attr("d", arc)
        .attr("stroke", "var(--surface)")
        .attr("stroke-width", "2px")
        .style("opacity", 0)
        .transition().duration(800).ease(d3.easeCubicOut)
        .attrTween("d", function(d) {
            const i = d3.interpolate({startAngle: 0, endAngle: 0}, d);
            return t => arc(i(t));
        })
        .style("opacity", 1);
        
    // Total in center
    const total = d3.sum(data, d => d.value);
    g.append("text")
        .attr("text-anchor", "middle")
        .attr("dy", "0.3em")
        .style("font-family", "var(--mono)")
        .style("font-size", "18px")
        .style("font-weight", "600")
        .style("fill", "var(--ink)")
        .text(total);
}

// 3. Reachability — the buyer's real question: "how many of these can I actually contact?"
// Every number here is counted from the served records (GET /stats -> reachability);
// nothing is asserted. A firm's generic inbox is deliberately NOT counted as a route
// to a person, because it is not one.
export function renderReachability(stats) {
    const el = document.getElementById("vis-reachability");
    if (!el || !stats || !stats.reachability) return;
    const r = stats.reachability, n = stats.records || 1;
    const rows = [
        ["Reachable at a named decision-maker", r.named_person_route, "hi"],
        ["Decision-maker known, no contact route yet", r.named_person_identified_no_route, "mid"],
        ["Firm switchboard/inbox only — not a person", r.firm_inbox_only, "lo"],
        ["No contact information found", r.no_contact_information, "lo"],
    ];
    el.innerHTML = rows.map(([label, val, cls]) => `
        <div class="reach-row">
          <div class="reach-top"><span>${label}</span><b>${val} of ${n}</b></div>
          <div class="reach-bar"><i class="${cls}" style="width:${Math.round(100*val/n)}%"></i></div>
        </div>`).join("");
}

// 4. Evidence strength — how many independent sources stand behind each record.
// Counted from the served records, not claimed.
export function renderEvidenceStrength(stats) {
    const el = document.getElementById("vis-evidence-strength");
    if (!el || !stats || !stats.evidence_strength) return;
    const e = stats.evidence_strength, n = stats.records || 1;
    const rows = [
        ["Corroborated by 2+ independent sources", e.two_or_more_sources, "hi"],
        ["Single source only", e.one_source, "mid"],
        ["No verification source on file", e.no_sources, "lo"],
    ];
    el.innerHTML = rows.map(([label, val, cls]) => `
        <div class="reach-row">
          <div class="reach-top"><span>${label}</span><b>${val} of ${n}</b></div>
          <div class="reach-bar"><i class="${cls}" style="width:${Math.round(100*val/n)}%"></i></div>
        </div>`).join("");
}

// 5. Geographic distribution — counted directly from the served records' hq_country
// field (GET /records). No geocoding, no invented coordinates: a country either has
// N verified firms on file or it doesn't.
export function renderGeoDistribution(records) {
    const el = document.getElementById("vis-geo-distribution");
    if (!el) return;
    const counts = new Map();
    for (const r of records) {
        const c = (r.country || "").trim();
        if (!c) continue;
        counts.set(c, (counts.get(c) || 0) + 1);
    }
    const rows = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 12);
    const withLoc = records.filter(r => r.country).length;
    if (!rows.length) {
        el.innerHTML = `<div class="empty">No headquarters country on file.</div>`;
        return;
    }
    const max = rows[0][1];
    el.innerHTML = rows.map(([name, val]) => `
        <div class="reach-row">
          <div class="reach-top"><span>${name}</span><b>${val}</b></div>
          <div class="reach-bar"><i class="hi" style="width:${Math.round(100 * val / max)}%"></i></div>
        </div>`).join("") +
        `<div class="panel-note" style="margin-top:10px;margin-bottom:0;">Headquarters country on file for
          ${withLoc} of ${records.length} firms.</div>`;
}

// 6. Network Graph (Entities & Evidence)
export function renderNetworkGraph(containerId, records) {
    const res = responsiveSvg(containerId, 220);
    if (!res) return;
    const { svg, width, height } = res;
    
    const nodes = [{id: "Query", group: 0}];
    const links = [];
    
    records.forEach((r, i) => {
        nodes.push({id: r.name, group: 1, type: r.type});
        links.push({source: "Query", target: r.name});
        
        if (r.principal) {
            nodes.push({id: r.principal, group: 2});
            links.push({source: r.name, target: r.principal});
        }
        
        (r.verification || []).forEach(v => {
            const vId = v + "_" + i;
            nodes.push({id: vId, label: v, group: 3});
            links.push({source: r.name, target: vId});
        });
    });
    
    const simulation = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(links).id(d => d.id).distance(40))
        .force("charge", d3.forceManyBody().strength(-60))
        .force("center", d3.forceCenter(width / 2, height / 2));
        
    const link = svg.append("g")
        .selectAll("line")
        .data(links)
        .join("line")
        .attr("stroke", "var(--line)")
        .attr("stroke-width", 1.5);
        
    const colors = ["var(--ink)", "var(--accent)", "var(--cite)", "var(--warn)"];
    
    const node = svg.append("g")
        .selectAll("circle")
        .data(nodes)
        .join("circle")
        .attr("r", d => d.group === 0 ? 8 : (d.group === 1 ? 6 : 4))
        .attr("fill", d => colors[d.group])
        .attr("stroke", "var(--surface)")
        .attr("stroke-width", 1.5);
        
    node.append("title").text(d => d.label || d.id);
        
    simulation.on("tick", () => {
        link.attr("x1", d => d.source.x).attr("y1", d => d.source.y)
            .attr("x2", d => d.target.x).attr("y2", d => d.target.y);
        node.attr("cx", d => d.x = Math.max(8, Math.min(width - 8, d.x)))
            .attr("cy", d => d.y = Math.max(8, Math.min(height - 8, d.y)));
    });
}
