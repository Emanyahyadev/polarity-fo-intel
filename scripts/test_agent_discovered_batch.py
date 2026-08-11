"""
Enrich + gate candidates that came from this system's OWN discovery agents
(SEC EDGAR, IAPD, IRS 990-PF, directory, news, web search) — explicitly
EXCLUDING the browser-use.com import (SourceClass.OTHER), so what gets
appended to the deliverable is genuinely agent-discovered, not backfilled
from an external lead list.

Persists released records into the CANONICAL STORE (data/final/records.json)
with their real per-field provenance intact (not a lossy CSV round-trip),
then re-derives CSV/XLSX/embeddings from the store via the same path
scripts/reexport_from_store.py uses — so results survive the autonomous
operating cycle's own re-export instead of being reverted by it.

Also applies a post-gate name-plausibility check for web-search-discovered
records (WEB/EXA/SERP): those sources extract a name via regex from a
search snippet, which sometimes grabs a sentence fragment instead of an
entity name (see commit a667581). A record is held back if its name doesn't
appear, in any recognizable form, in its own website domain or fetched
description — catching "Chart of Family Office" (a directory page) and
similar garbage before it reaches the deliverable. This does NOT catch a
site that correctly names itself but is actually a bank/media company
wrongly self-describing as a family office (see "Family Office Networks");
that needs the classify() fix noted in a667581, not this heuristic.

    python scripts/test_agent_discovered_batch.py --limit 200 --persist
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from fointel.assemble import enrich_and_build
from fointel.export import export_dataset
from fointel.rag.index import precompute_and_save
from fointel.schema import AuditEntry, FamilyOfficeRecord, SourceClass
from fointel.store import get_repository
from fointel.validation.gates import ReleaseGate

RECORDS_PATH = Path("data/final/records.json")
AUDIT_PATH = Path("data/final/audit.json")
CSV_PATH = Path("data/final/family_offices.csv")

WEB_SOURCES = {SourceClass.WEB, SourceClass.EXA, SourceClass.SERP}


def _squash(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _name_plausible(r: FamilyOfficeRecord) -> bool:
    """Post-gate safety net for web-search-discovered names (see module docstring)."""
    if r.discovery_source not in WEB_SOURCES:
        return True
    core = r.name.strip()
    if core.lower().endswith("family office"):
        core = core[: -len("family office")].strip()
    if not core:
        return False
    squashed_core = _squash(core)
    if not squashed_core:
        return False
    domain_squashed = _squash(r.website or "")
    if squashed_core in domain_squashed:
        return True
    if core.lower() in (r.description or "").lower():
        return True
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--persist", action="store_true",
                     help="write released records into the canonical store and re-export")
    args = ap.parse_args()

    as_of = datetime.now(timezone.utc).date()
    repo = get_repository()

    existing_ids = set()
    existing_names = set()
    if RECORDS_PATH.exists():
        existing = json.loads(RECORDS_PATH.read_text(encoding="utf-8"))
        existing_ids = {r["fo_id"] for r in existing}
        existing_names = {r["name"].lower() for r in existing}

    candidates = [c for c in repo.all_candidates()
                  if c.source_class != SourceClass.OTHER
                  and c.name.lower() not in existing_names]
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

    plausible = [r for r in released if _name_plausible(r)]
    held_for_review = [r for r in released if not _name_plausible(r)]

    print("\n===== DISCOVERY REPORT =====")
    print(json.dumps(discovery, indent=2, ensure_ascii=False))
    print("\n===== GATE =====")
    print(f"discovered:                 {len(candidates)}")
    print(f"collected (built, pre-gate): {len(records)}")
    print(f"  of which qualified:       {discovery.get('total_qualified', 'n/a')}")
    print(f"released by gate:           {len(released)}")
    print(f"  held back (name check):   {len(held_for_review)}")
    print(f"  passing to deliverable:   {len(plausible)}")
    print(f"withheld gate reasons:      {dict(withheld)}")
    if held_for_review:
        print("\n===== HELD FOR REVIEW (name-plausibility check failed) =====")
        for r in held_for_review:
            print(f"  {r.name} | website={r.website} | discovery={r.discovery_source.value}")
    print("\n===== RELEASED TO DELIVERABLE =====")
    for r in plausible:
        print(f"  {r.name} | {r.fo_type.value} | {r.record_confidence.value} | "
              f"discovery={r.discovery_source.value if r.discovery_source else '?'}")

    if args.persist and plausible:
        new_by_id = {r.fo_id: r for r in plausible if r.fo_id not in existing_ids}
        existing = json.loads(RECORDS_PATH.read_text(encoding="utf-8")) if RECORDS_PATH.exists() else []
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
              f"provenance rows {res['provenance_rows']} | audit rows {len(audit)} | "
              f"embeddings docs={shapes[0]} focus={shapes[1]}")


if __name__ == "__main__":
    main()
