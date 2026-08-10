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
from fointel.evidence import new_manifest, utc_now_iso, write_manifest
from fointel.export import export_dataset
from fointel.store import get_repository
from fointel.validation.gates import ReleaseGate
from fointel.validation.selection import select_final
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap candidates (0 = all)")
    ap.add_argument("--target", type=int, default=50)
    ap.add_argument("--export", action="store_true", help="write the deliverable + evidence")
    args = ap.parse_args()

    started_at = utc_now_iso()
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
    print(f"discovered:                 {discovery.get('total_discovered', len(candidates))}")
    print(f"collected (built, pre-gate): {len(records)}")
    print(f"  of which qualified:       {discovery.get('total_qualified', 'n/a')}")
    print(f"released by gate:           {len(released)}")
    print(f"withheld gate reasons:      {dict(withheld)}")
    print("\n===== SELECTION =====")
    print(json.dumps(selection, indent=2, ensure_ascii=False))
    conf = Counter(r.record_confidence.value for r in selected)
    types = Counter(r.fo_type.value for r in selected)
    print(f"selected confidence: {dict(conf)}")
    print(f"selected types:      {dict(types)}")

    print("\n===== RELEASED RECORDS (quality inspection) =====")
    for r in sorted(released, key=lambda x: x.discovery_source.value):
        vs = ",".join(sorted({s.source_class.value.split()[0] for s in r.verification_sources}))
        disc = r.discovery_source.value.split()[0]
        geo = f"{r.hq_city or '?'},{r.hq_state or '?'},{r.hq_country or '?'}"
        print(f"  [{disc:6}] {r.name[:34]:34} {r.fo_type.value[:12]:12} {r.record_confidence.value:6} "
              f"geo={geo[:22]:22} verify=[{vs}] phone={'Y' if r.hq_phone else '-'}")

    if args.export:
        # Recent-news signals (GDELT) for the DELIVERED set only. GDELT requires ~6s between
        # calls, so scoping to the 50 shipped records (not the ~400-firm pool) keeps this to
        # a few minutes. News is appended after any 13F recent-investment signal; coverage is
        # genuinely sparse for private family offices, so many records honestly gain none.
        import time
        from fointel.enrichment.signals import SignalsEnricher
        sig_enr = SignalsEnricher()
        news_added, deadline = 0, time.monotonic() + 300  # hard cap: never exceed ~5 min
        for rec in selected:
            if time.monotonic() > deadline:
                print("news step hit its time cap; remaining firms left without news (honest)")
                break
            room = 3 - len(rec.signals)
            if room <= 0:
                continue
            for s in sig_enr.firm_signals(rec.name, max_signals=min(2, room)):
                if len(rec.signals) >= 3:
                    break
                rec.signals.append(s)
                news_added += 1
        print(f"\n===== NEWS SIGNALS =====\nadded {news_added} GDELT news signal(s) across the delivered 50")

        result = export_dataset(selected, audit=[], out_dir="data/final")
        Path("docs/evidence").mkdir(parents=True, exist_ok=True)
        Path("docs/evidence/dataset-discovery-report.json").write_text(
            json.dumps({**discovery, "released": len(released),
                        "withheld_gate_reasons": dict(withheld),
                        "selected": len(selected), "selection": selection,
                        "confidence": dict(conf), "types": dict(types)},
                       indent=2, ensure_ascii=False), encoding="utf-8")
        manifest = new_manifest(stage="dataset", started_at=started_at, counts={
            "discovered": discovery["total_discovered"],
            "collected_pre_gate": len(records),
            "qualified_pre_gate": discovery.get("total_qualified", 0),
            "released": len(released),
            "delivered": len(selected)}, notes={"export": result})
        write_manifest(manifest)
        print(f"\n===== EXPORT =====\n{json.dumps(result, indent=2)}")

        from fointel.rag.index import precompute_and_save
        docs_shape, focus_shape = precompute_and_save(selected)
        print(f"\n===== EMBEDDINGS =====\nRecomputed RAG index: {docs_shape[0]} documents")


if __name__ == "__main__":
    main()
