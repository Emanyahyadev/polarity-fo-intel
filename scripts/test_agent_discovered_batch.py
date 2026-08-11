"""
Enrich + gate candidates that came from this system's OWN discovery agents
(SEC EDGAR, IAPD, IRS 990-PF, directory, news, web search) — explicitly
EXCLUDING the browser-use.com import (SourceClass.OTHER), so what gets
appended to the deliverable is genuinely agent-discovered, not backfilled
from an external lead list.

    python scripts/test_agent_discovered_batch.py --limit 100 --append-csv
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from fointel.assemble import enrich_and_build
from fointel.schema import SourceClass
from fointel.store import get_repository
from fointel.validation.gates import ReleaseGate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--append-csv", action="store_true")
    args = ap.parse_args()

    as_of = datetime.now(timezone.utc).date()
    repo = get_repository()

    existing_names = set()
    csv_path = Path("data/final/family_offices.csv")
    if csv_path.exists():
        existing_names = set(pd.read_csv(csv_path)["family_office_name"].str.lower())

    candidates = [c for c in repo.all_candidates()
                  if c.source_class != SourceClass.OTHER
                  and c.name.lower() not in existing_names]
    # bias toward likely-qualifiers so a bounded slice is informative
    candidates = sorted(candidates, key=lambda c: "family office" not in c.name.lower())
    if args.limit:
        candidates = candidates[:args.limit]

    print(f"testing {len(candidates)} agent-discovered candidates "
          f"(not already in the deliverable, not from the browser-use import)")
    records, discovery = enrich_and_build(candidates, as_of)

    gate = ReleaseGate()
    released, outcomes = gate.publish(records)
    withheld = Counter()
    for o in outcomes:
        if not o.passed:
            for c in o.failures():
                withheld[c.name] += 1

    print("\n===== DISCOVERY REPORT =====")
    print(json.dumps(discovery, indent=2, ensure_ascii=False))
    print("\n===== GATE =====")
    print(f"discovered:                 {len(candidates)}")
    print(f"collected (built, pre-gate): {len(records)}")
    print(f"  of which qualified:       {discovery.get('total_qualified', 'n/a')}")
    print(f"released by gate:           {len(released)}")
    print(f"withheld gate reasons:      {dict(withheld)}")
    print("\n===== RELEASED (would ship) =====")
    for r in released:
        print(f"  {r.name} | {r.fo_type.value} | {r.record_confidence.value} | "
              f"discovery={r.discovery_source.value if r.discovery_source else '?'}")

    if args.append_csv:
        existing = pd.read_csv(csv_path) if csv_path.exists() else pd.DataFrame()
        new_rows = pd.DataFrame([r.to_delivery_row() for r in released])
        before = len(existing)
        combined = pd.concat([existing, new_rows], ignore_index=True)
        if "fo_id" in combined.columns:
            combined = combined.drop_duplicates(subset="fo_id", keep="first")
        combined.to_csv(csv_path, index=False, encoding="utf-8")
        print(f"\n===== CSV APPEND =====\n{csv_path}: {before} -> {len(combined)} rows "
              f"({len(combined) - before} net new)")


if __name__ == "__main__":
    main()
