"""
Import an externally-sourced NDJSON lead list into the candidate pool.

    python scripts/import_candidates.py data/raw/browseruse_2026-08-10.ndjson

Each line becomes a `Candidate` ONLY — name, source, source URL, discovery
timestamp, plus everything else parked as unverified `hints`/`raw`. This is a
lead list, not a verified dataset: none of its fields (email, phone, address,
"verification_status") were produced by this pipeline's own enrichment, so
none of them may be trusted or copied into a FamilyOfficeRecord directly.
Once imported, these candidates go through the normal
enrich_and_build -> ReleaseGate path like every other source, so their claims
get independently re-derived (or dropped) before anything could ship.
"""

from __future__ import annotations

import argparse
import json
from datetime import date

from fointel.schema import Candidate, SourceClass
from fointel.store import get_repository
from fointel.text import norm_name


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="NDJSON file, one lead object per line")
    args = ap.parse_args()

    repo = get_repository()
    candidates = []
    with open(args.path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            lead = json.loads(line)
            name = (lead.get("candidate_name") or "").strip()
            if not name:
                continue
            website = lead.get("website") or None
            candidates.append(Candidate(
                name=name,
                source_class=SourceClass.OTHER,
                source_url=website,
                discovered_at=date.today(),
                dedup_key=norm_name(name),
                discovery_sources=["browser-use.com lead list (unverified)"],
                # Full external payload kept for provenance/audit, but NOT
                # treated as verified — enrichment re-derives everything.
                raw=lead,
                hints={"country": lead.get("country") or None,
                       "city": lead.get("city") or None,
                       "possible_type": lead.get("possible_type") or None},
            ))

    added = repo.add_candidates(candidates)
    print(f"parsed {len(candidates)} leads, added {added} new candidates "
          f"(rest were duplicates by dedup_key)")
    print("These are UNVERIFIED candidates. Run scripts/build_dataset.py to "
          "enrich, classify, and gate them before anything can release.")


if __name__ == "__main__":
    main()
