"""
Build the validated dataset: enrich + build -> release gate -> balanced selection.

    python scripts/build_dataset.py --limit 8      # quick slice for verification
    python scripts/build_dataset.py                # full pool

Prints the discovery report, gate pass/withhold counts, and the selected-50
source distribution. Export of the delivered file is a follow-up step once the
count is confirmed.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone

from fointel.assemble import enrich_and_build
from fointel.store import get_repository
from fointel.validation.gates import ReleaseGate
from fointel.validation.selection import select_final


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap candidates (0 = all)")
    ap.add_argument("--target", type=int, default=50)
    args = ap.parse_args()

    as_of = datetime.now(timezone.utc).date()
    repo = get_repository()
    candidates = repo.all_candidates()
    if args.limit:
        # bias the slice toward likely-qualifiers so a small run is informative
        candidates = sorted(candidates, key=lambda c: "family office" not in c.name.lower())[:args.limit]

    records, discovery = enrich_and_build(candidates, as_of)

    gate = ReleaseGate()
    released, outcomes = gate.publish(records)

    # why records were withheld by the gate
    withheld = Counter()
    for o in outcomes:
        if not o.passed:
            for c in o.failures():
                withheld[c.name] += 1

    selected, selection = select_final(released, target=args.target)

    print("\n===== DISCOVERY REPORT =====")
    print(json.dumps(discovery, indent=2, ensure_ascii=False))
    print("\n===== GATE =====")
    print(f"built (qualified pre-gate): {len(records)}")
    print(f"released by gate:           {len(released)}")
    print(f"withheld gate reasons:      {dict(withheld)}")
    print("\n===== SELECTION =====")
    print(json.dumps(selection, indent=2, ensure_ascii=False))
    conf = Counter(r.record_confidence.value for r in selected)
    types = Counter(r.fo_type.value for r in selected)
    print(f"selected confidence: {dict(conf)}")
    print(f"selected types:      {dict(types)}")


if __name__ == "__main__":
    main()
