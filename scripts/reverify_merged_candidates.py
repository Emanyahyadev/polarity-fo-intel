"""
Enrich + gate the 54 candidates another concurrent session merged directly
into family_offices.csv with self-labeled "not independently verified"
evidence, bypassing classify()/ReleaseGate entirely. Routes them through the
real pipeline: independently re-derive evidence, gate, persist to the
canonical store only if they actually clear G1-G9.

    python scripts/reverify_merged_candidates.py --persist
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fointel.assemble import enrich_and_build
from fointel.export import export_dataset
from fointel.rag.index import precompute_and_save
from fointel.schema import AuditEntry, FamilyOfficeRecord
from fointel.store import get_repository
from fointel.validation.gates import ReleaseGate

MARKER = "other-session browser-use merge (routing through real gate)"
RECORDS_PATH = Path("data/final/records.json")
AUDIT_PATH = Path("data/final/audit.json")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist", action="store_true")
    args = ap.parse_args()

    as_of = datetime.now(timezone.utc).date()
    repo = get_repository()
    candidates = [c for c in repo.all_candidates() if MARKER in (c.discovery_sources or [])]
    print(f"re-verifying {len(candidates)} candidates from the other session's merge")

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
    print("\n===== RELEASED (independently re-verified) =====")
    for r in released:
        print(f"  {r.name} | {r.fo_type.value} | {r.record_confidence.value}")
    print("\n===== NOT CLEARED (stays out of the deliverable) =====")
    for c in candidates:
        if c.name not in {r.name for r in released}:
            print(f"  {c.name}")

    if args.persist and released:
        existing = json.loads(RECORDS_PATH.read_text(encoding="utf-8")) if RECORDS_PATH.exists() else []
        existing_ids = {r["fo_id"] for r in existing}
        new_by_id = {r.fo_id: r for r in released if r.fo_id not in existing_ids}
        combined_json = existing + [r.model_dump(mode="json") for r in new_by_id.values()]
        RECORDS_PATH.write_text(json.dumps(combined_json, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"\n===== CANONICAL STORE =====\n{RECORDS_PATH}: {len(existing)} -> "
              f"{len(combined_json)} records ({len(new_by_id)} net new)")

        all_records = [FamilyOfficeRecord.model_validate(d) for d in combined_json]
        audit = ([AuditEntry.model_validate(a) for a in json.loads(AUDIT_PATH.read_text(encoding="utf-8"))]
                  if AUDIT_PATH.exists() else [])
        res = export_dataset(all_records, audit=audit, out_dir="data/final")
        shapes = precompute_and_save(all_records)
        print(f"===== RE-EXPORT =====\n{res['records']} records | "
              f"provenance rows {res['provenance_rows']} | embeddings docs={shapes[0]}")


if __name__ == "__main__":
    main()
