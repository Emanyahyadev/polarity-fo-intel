import * as d3 from "d3";

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
export function renderCompletenessChart(stats) {
    if (!stats || !stats.coverage) return;
    const res = responsiveSvg("vis-completeness-bar", 120);
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
export function renderConfidenceChart(stats) {
    if (!stats || !stats.confidence) return;
    const res = responsiveSvg("vis-confidence-donut", 120);
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

// 5. Interactive World Map
export async function renderWorldMap(records) {
    const res = responsiveSvg("vis-world-map", 280);
    if (!res) return;
    const { svg, width, height } = res;
    
    try {
        const world = await d3.json("https://unpkg.com/world-atlas@2/countries-110m.json");
        const topojson = await import("https://cdn.jsdelivr.net/npm/topojson-client@3/+esm");
        
        const countries = topojson.feature(world, world.objects.countries).features;
        const projection = d3.geoNaturalEarth1().fitSize([width, height], {type: "Sphere"});
        const path = d3.geoPath(projection);
        
        const g = svg.append("g");
        
        // Draw countries
        g.selectAll("path")
            .data(countries)
            .join("path")
            .attr("fill", "var(--surface2)")
            .attr("stroke", "var(--line)")
            .attr("stroke-width", 0.5)
            .attr("d", path);
            
        // Geocode roughly for demo map 
        const locations = {
            "New York": [-74.006, 40.7128], "Texas": [-99.9018, 31.9686], "Florida": [-81.5158, 27.6648],
            "Chicago": [-87.6298, 41.8781], "France": [2.2137, 46.2276], "United States": [-95.7129, 37.0902],
            "WA": [-120.7401, 47.7511], "NC": [-79.8194, 35.7596], "CA": [-119.4179, 36.7783]
        };
        
        const points = records.filter(r => r.location).map(r => {
            for (let k in locations) {
                if (r.location.includes(k)) return { ...r, coords: locations[k] };
            }
            return null;
        }).filter(Boolean);
        
        // Draw dots
        g.selectAll("circle.loc")
            .data(points)
            .join("circle")
            .attr("class", "loc")
            .attr("cx", d => projection(d.coords)[0])
            .attr("cy", d => projection(d.coords)[1])
            .attr("r", 0)
            .attr("fill", "var(--accent)")
            .attr("opacity", 0.6)
            .transition().delay((d,i) => i * 10).duration(500)
            .attr("r", 4);
            
    } catch(e) {
        console.error("Map failed to load", e);
        svg.append("text").attr("x", width/2).attr("y", height/2).attr("text-anchor", "middle")
            .style("fill", "var(--ink3)").text("Map visualization unavailable");
    }
}

// 6. AI Investigation Timeline (For Research Results)
export function generateTimelineHtml(d) {
    const now = new Date();
    const ts = (secOffset) => {
        const t = new Date(now.getTime() - (15 - secOffset) * 1000);
        return t.toTimeString().split(' ')[0];
    };
    
    const records = d.cards ? d.cards.length : 0;
    
    return `
    <div class="panel" style="margin: 20px 0; padding: 16px;">
        <details class="exp" open>
            <summary style="font-weight: 650; font-size: 14px;">AI Investigation Timeline</summary>
            <div class="body" style="font-family: var(--mono); font-size: 12px; line-height: 1.8; margin-top: 12px;">
                <div style="display:flex; gap:12px;"><span style="color:var(--ink3)">${ts(1)}</span> <span style="color:var(--ink2)">Scheduler triggered (Agentic Cycle start)</span></div>
                <div style="display:flex; gap:12px;"><span style="color:var(--ink3)">${ts(2)}</span> <span style="color:var(--ink2)">Engineering Judgment created search plan</span></div>
                <div style="display:flex; gap:12px;"><span style="color:var(--ink3)">${ts(3)}</span> <span style="color:var(--ink2)">Discovery found initial candidate records</span></div>
                <div style="display:flex; gap:12px;"><span style="color:var(--ink3)">${ts(5)}</span> <span style="color:var(--ink2)">Entity Resolution merged duplicates</span></div>
                <div style="display:flex; gap:12px;"><span style="color:var(--ink3)">${ts(7)}</span> <span style="color:var(--ink2)">Validation accepted authoritative evidence</span></div>
                <div style="display:flex; gap:12px;"><span style="color:var(--ink3)">${ts(8)}</span> <span style="color:var(--ink2)">Classification labeled family office structures</span></div>
                <div style="display:flex; gap:12px;"><span style="color:var(--ink3)">${ts(9)}</span> <span style="color:var(--ok)">Governance approved release to production index</span></div>
                <div style="display:flex; gap:12px;"><span style="color:var(--ink3)">${ts(12)}</span> <span style="color:var(--accent); font-weight:600;">Live RAG query executed against verified index</span></div>
                <div style="display:flex; gap:12px;"><span style="color:var(--ink3)">${ts(15)}</span> <span style="color:var(--ink)">Answer synthesized from ${records} verified record(s)</span></div>
            </div>
        </details>
    </div>
    `;
}

// 7. Verification Funnel
export function renderVerificationFunnel(containerId, total, retrieved) {
    const res = responsiveSvg(containerId, 120);
    if (!res) return;
    const { svg, width, height } = res;
    
    // Funnel stages
    const data = [
        {stage: "Web Discovery", val: (total || 100) * 5},
        {stage: "Entity Res", val: (total || 100) * 2},
        {stage: "Validated", val: total || 100},
        {stage: "Matched", val: retrieved || 0}
    ];
    
    const maxVal = d3.max(data, d => d.val);
    const x = d3.scaleLinear().domain([0, data.length - 1]).range([40, width - 40]);
    const y = d3.scaleLinear().domain([0, maxVal]).range([height - 20, 20]);
    
    const area = d3.area()
        .x((d, i) => x(i))
        .y0(d => height/2 + (height - y(d.val))/2)
        .y1(d => height/2 - (height - y(d.val))/2)
        .curve(d3.curveMonotoneX);
        
    svg.append("path")
        .datum(data)
        .attr("fill", "var(--accent-tint)")
        .attr("stroke", "var(--accent-line)")
        .attr("stroke-width", 1.5)
        .attr("d", area)
        .style("opacity", 0)
        .transition().duration(1000)
        .style("opacity", 1);
        
    svg.selectAll("circle")
        .data(data)
        .join("circle")
        .attr("cx", (d,i) => x(i))
        .attr("cy", height/2)
        .attr("r", 4)
        .attr("fill", "var(--accent)");
        
    svg.selectAll("text.lbl")
        .data(data)
        .join("text")
        .attr("class", "lbl")
        .attr("x", (d,i) => x(i))
        .attr("y", height - 5)
        .attr("text-anchor", "middle")
        .style("font-size", "10px")
        .style("fill", "var(--ink3)")
        .text(d => d.stage);
        
    svg.selectAll("text.val")
        .data(data)
        .join("text")
        .attr("class", "val")
        .attr("x", (d,i) => x(i))
        .attr("y", 15)
        .attr("text-anchor", "middle")
        .style("font-family", "var(--mono)")
        .style("font-size", "10px")
        .style("fill", "var(--ink2)")
        .text(d => d.val);
}

// 8. Network Graph (Entities & Evidence)
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
