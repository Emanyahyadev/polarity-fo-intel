"""
Capture a live-URL query transcript as reproducible evidence.

Hits the deployed Micro-RAG (health + a fixed set of on- and off-topic queries)
and writes both a machine-readable JSON artifact and a human-readable Markdown
transcript under docs/evidence. The off-topic query is included on purpose to
show the grounding control abstaining on live traffic rather than guessing.

Reproduce:
    py -3.12 scripts/capture_live_evidence.py [BASE_URL]
    # default BASE_URL = https://family-office-intelligence.onrender.com
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE = (sys.argv[1] if len(sys.argv) > 1 else
        "https://family-office-intelligence.onrender.com").rstrip("/")

QUERIES = [
    "multi-family offices in Texas",                  # structured: type + state
    "family offices with AUM over $1 billion",        # structured: numeric AUM filter
    "single-family offices in Belgium",               # international single-family office (Korys)
    "Tell me about WE Family Offices",                # entity attributes (MFO, ADV AUM, principal)
    "family offices in California",                    # semantic + location
    "best pizza office in Chicago",                    # in-vocabulary probe -> must abstain
    "family offices headquartered on the moon",        # in-vocabulary probe -> must abstain
]

OUT = Path(__file__).resolve().parents[1] / "docs" / "evidence"


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    health = requests.get(f"{BASE}/health", timeout=60).json()

    results = []
    for q in QUERIES:
        r = requests.post(f"{BASE}/query", json={"query": q}, timeout=60).json()
        results.append({
            "query": q,
            "answered": r["answered"],
            "mode": r["mode"],
            "reason": r["reason"],
            "answer": r["answer"],
            "citations": r.get("citations", []),
            "cards": [{"name": c["name"], "type": c["type"], "location": c["location"],
                       "principal": c.get("principal"), "aum": c.get("aum"),
                       "signals": c.get("signals"), "confidence": c["confidence"],
                       "verification": c["verification"], "match": c["match"]}
                      for c in r.get("cards", [])],
        })

    payload = {"captured_at_utc": ts, "base_url": BASE, "health": health, "queries": results}
    (OUT / "live-url-query-transcript.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [f"# Live URL — query transcript",
             "",
             f"- **URL:** {BASE}",
             f"- **Captured (UTC):** {ts}",
             f"- **Health:** `{json.dumps(health)}`",
             "",
             "Reproduce: `py -3.12 scripts/capture_live_evidence.py`",
             ""]
    for r in results:
        verdict = "ANSWERED" if r["answered"] else "ABSTAINED"
        lines += [f"## {r['query']}",
                  "",
                  f"**{verdict}** · mode `{r['mode']}` · {r['reason']}",
                  "",
                  "```",
                  r["answer"],
                  "```",
                  ""]
        if r["cards"]:
            lines.append("Records (name · type · location · confidence · verified-via · match):")
            lines.append("")
            for c in r["cards"]:
                lines.append(
                    f"- {c['name']} · {c['type']} · {c['location']} · "
                    f"{c['confidence']} · {', '.join(c['verification'])} · {c['match']}")
            lines.append("")
    (OUT / "live-url-query-transcript.md").write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {OUT/'live-url-query-transcript.json'}")
    print(f"Wrote {OUT/'live-url-query-transcript.md'}")
    print(f"Health: {health} | queries: {len(results)} "
          f"(answered {sum(r['answered'] for r in results)}, "
          f"abstained {sum(not r['answered'] for r in results)})")


if __name__ == "__main__":
    main()
