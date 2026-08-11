"""
Ingest the browser-use "new country discovery" candidates
(family_office_discovery/output/new_countries_candidates.jsonl) into the
canonical candidate store, then route them through the real pipeline
(enrich_and_build + ReleaseGate) exactly like reverify_merged_candidates.py
did for the earlier raw CSV merge. Only candidates that independently
clear G1-G9 get persisted to data/final/records.json and re-exported.

    python scripts/ingest_and_reverify_new_countries.py --persist
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from fointel.assemble import enrich_and_build
from fointel.export import export_dataset
from fointel.rag.index import precompute_and_save
from fointel.schema import AuditEntry, Candidate, FamilyOfficeRecord, SourceClass
from fointel.store import get_repository
from fointel.validation.gates import ReleaseGate

MARKER = "browser-use new-country discovery (routing through real gate)"
CANDIDATES_PATH = Path("family_office_discovery/output/new_countries_candidates.jsonl")
RECORDS_PATH = Path("data/final/records.json")
AUDIT_PATH = Path("data/final/audit.json")


def norm_name(name: str) -> str:
    n = (name or "").lower().strip()
    n = re.sub(r"[.,]", "", n)
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    n = re.sub(r"\bthe\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def load_new_candidates() -> list[Candidate]:
    today = date.today()
    out = []
    with open(CANDIDATES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            name = d.get("candidate_name")
            if not name:  # zero-result marker rows
                continue
            website = d.get("website") or ""
            out.append(Candidate(
                name=name,
                source_class=SourceClass.OTHER,
                source_url=website or None,
                discovered_at=today,
                dedup_key=norm_name(name),
                discovery_sources=[MARKER],
                raw={
                    "candidate_name": name,
                    "possible_type": d.get("possible_type"),
                    "country": d.get("country"),
                    "city": d.get("city"),
                    "website": website,
                    "discovery_source": d.get("discovery_source"),
                    "discovery_reason": d.get("discovery_reason"),
                },
                hints={"website": website, "city": d.get("city"), "country": d.get("country")},
            ))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persist", action="store_true")
    args = ap.parse_args()

    as_of = datetime.now(timezone.utc).date()
    repo = get_repository()

    new_candidates = load_new_candidates()
    added = repo.add_candidates(new_candidates)
    print(f"loaded {len(new_candidates)} candidates from {CANDIDATES_PATH}, "
          f"{added} newly added to the canonical store (rest were dupes already known)")

    candidates = [c for c in repo.all_candidates() if MARKER in (c.discovery_sources or [])]
    print(f"re-verifying {len(candidates)} marked candidates through the real pipeline")

    records, discovery = enrich_and_build(candidates, as_of)
    gate = ReleaseGate()
    released, outcomes = gate.publish(records)
    withheld = Counter()
    for o in outcomes:
        if not o.passed:
            for c in o.failures():
                withheld[c.name] += 1

    print("\n===== GATE =====")
    print(f"discovered:                  {len(candidates)}")
    print(f"collected (built, pre-gate):  {len(records)}")
    print(f"released by gate:             {len(released)}")
    print(f"withheld gate reasons:        {dict(withheld)}")
    print("\n===== RELEASED (independently re-verified) =====")
    for r in released:
        print(f"  {r.name} | {r.hq_country} | {r.fo_type.value} | {r.record_confidence.value}")

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
        precompute_and_save(all_records)
        print(f"===== RE-EXPORT =====\n{res['records']} records")


if __name__ == "__main__":
    main()
