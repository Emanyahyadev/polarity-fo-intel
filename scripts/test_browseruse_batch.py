"""
One-off verification run: enrich + gate ONLY the candidates imported from the
browser-use.com lead list (scripts/import_candidates.py), so their unverified
claims get independently checked rather than trusted. Not part of the regular
pipeline; delete once the import has been verified.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from fointel.assemble import enrich_and_build
from fointel.store import get_repository
from fointel.validation.gates import ReleaseGate

MARKER = "browser-use.com lead list (unverified)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--append-csv", action="store_true",
                     help="append gate-released rows to data/final/family_offices.csv (dedup by fo_id)")
    args = ap.parse_args()

    as_of = datetime.now(timezone.utc).date()
    repo = get_repository()
    candidates = [c for c in repo.all_candidates() if MARKER in (c.discovery_sources or [])]
    if args.offset:
        candidates = candidates[args.offset:]
    if args.limit:
        candidates = candidates[:args.limit]

    print(f"testing {len(candidates)} browser-use-sourced candidates")
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
        print(f"  {r.name} | {r.fo_type.value} | {r.record_confidence.value}")

    if args.append_csv:
        csv_path = Path("data/final/family_offices.csv")
        existing = pd.read_csv(csv_path) if csv_path.exists() else pd.DataFrame()
        new_rows = pd.DataFrame([r.to_delivery_row() for r in released])
        before = len(existing)
        combined = pd.concat([existing, new_rows], ignore_index=True)
        if "fo_id" in combined.columns:
            combined = combined.drop_duplicates(subset="fo_id", keep="first")
        combined.to_csv(csv_path, index=False, encoding="utf-8")
        print(f"\n===== CSV APPEND =====\n{csv_path}: {before} -> {len(combined)} rows "
              f"({len(combined) - before} net new)")

        if len(combined) != before:
            from fointel.rag import load as rag_load
            from fointel.rag.index import precompute_and_save
            all_records = rag_load.load_records_from_csv(str(csv_path))
            shapes = precompute_and_save(all_records)
            print(f"\n===== EMBEDDINGS =====\nrefreshed: docs={shapes[0]}, focus={shapes[1]}")


if __name__ == "__main__":
    main()
