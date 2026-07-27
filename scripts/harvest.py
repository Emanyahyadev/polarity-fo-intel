"""
CLI: run the discovery harvest, persist the candidate pool, and write evidence.

    python scripts/harvest.py --per-source 50

Writes:
  data/fointel.db                                  (candidate pool)
  docs/evidence/01-discovery-source-distribution.csv
  docs/evidence/01-discovery-harvest-summary.json
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from fointel.discovery.harvest import harvest
from fointel.evidence import new_manifest, utc_now_iso, write_manifest
from fointel.schema import SourceClass
from fointel.store import get_repository

# High-signal SEC pulls more; noisy 990-PF is capped; directory/news take what they have.
PER_SOURCE_LIMITS = {
    SourceClass.SEC_EDGAR.value: 120,
    SourceClass.IRS_990PF.value: 50,
    SourceClass.DIRECTORY.value: 60,
    SourceClass.NEWS.value: 40,
}


def main() -> None:
    ap = argparse.ArgumentParser(description="Discovery harvest -> candidate pool")
    ap.add_argument("--per-source", type=int, default=50,
                    help="fallback cap for any source without an explicit limit")
    ap.add_argument("--evidence-dir", default="docs/evidence")
    args = ap.parse_args()

    started_at = utc_now_iso()
    repo = get_repository()
    report = harvest(repo, args.per_source, limits=PER_SOURCE_LIMITS)

    ev = Path(args.evidence_dir)
    ev.mkdir(parents=True, exist_ok=True)

    # Run manifest — ties this pool to the exact code + inputs (reproducibility)
    res = report["resolution"]
    manifest = new_manifest(
        stage="discovery",
        started_at=started_at,
        counts={
            "discovered_yielded": report["total_yielded"],
            "resolved_firms": report["resolved_firms"],
            "merges": res["actions"].get("merge", 0),
            "possible_duplicates_kept_distinct": res["actions"].get(
                "possible_duplicate_kept_distinct", 0),
            "pool_size": report["pool_size"],
            "source_failures": sum(1 for i in report["per_source"].values() if "error" in i),
        },
        notes={"per_source": report["per_source"]},
    )
    write_manifest(manifest, args.evidence_dir)

    # Source distribution (evidence 01)
    with (ev / "01-discovery-source-distribution.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_class", "yielded", "error"])
        for source, info in report["per_source"].items():
            w.writerow([source, info.get("yielded", 0), info.get("error", "")])

    # Entity-resolution decision log (evidence 02) — one JSON line per decision
    decisions = report["resolution"].pop("decisions")
    with (ev / "02-entity-resolution-decisions.jsonl").open("w", encoding="utf-8") as f:
        for d in decisions:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    # Lean summary (evidence 01) — decisions live in the JSONL, not here
    (ev / "01-discovery-harvest-summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    printable = dict(report)
    printable["resolution"] = {k: v for k, v in report["resolution"].items()
                               if k != "multi_source_firms"}
    print(json.dumps(printable, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
