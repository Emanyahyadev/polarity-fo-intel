"""
Pipeline entry point.

    python scripts/run_pipeline.py discovery --per-source 50

Stages are added as they are implemented; each stage is a real, runnable command
(no placeholders). Wave 1 implements the `discovery` stage: run every discovery
source, resolve entities (evidence-based, logged), persist the candidate pool, and
write reproducibility evidence.

Writes:
  data/fointel.db                                     (candidate pool)
  docs/evidence/01-discovery-source-distribution.csv
  docs/evidence/01-discovery-harvest-summary.json
  docs/evidence/02-entity-resolution-decisions.jsonl
  docs/evidence/run-manifest-discovery-<runid>.json
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
    SourceClass.SEC_EDGAR.value: 140,   # 13F "family office" filers (finite ~34 qualify)
    SourceClass.SEC_IAPD.value: 200,    # registered family offices (the large, distinct lens)
    SourceClass.IRS_990PF.value: 60,
    SourceClass.DIRECTORY.value: 80,
    SourceClass.NEWS.value: 40,
    SourceClass.WEB.value: 50,          # Tavily web search (keyed, low rate unlike news)
    SourceClass.EXA.value: 50,          # EXA web search (keyed)
    SourceClass.SERP.value: 50,         # Serper web search (keyed)
}


def run_discovery(per_source: int, evidence_dir: str) -> dict:
    started_at = utc_now_iso()
    repo = get_repository()
    report = harvest(repo, per_source, limits=PER_SOURCE_LIMITS)

    ev = Path(evidence_dir)
    ev.mkdir(parents=True, exist_ok=True)

    with (ev / "01-discovery-source-distribution.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["source_class", "yielded", "error"])
        for source, info in report["per_source"].items():
            w.writerow([source, info.get("yielded", 0), info.get("error", "")])

    decisions = report["resolution"].pop("decisions")
    with (ev / "02-entity-resolution-decisions.jsonl").open("w", encoding="utf-8") as f:
        for d in decisions:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    (ev / "01-discovery-harvest-summary.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    res = report["resolution"]
    manifest = new_manifest(
        stage="discovery", started_at=started_at,
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
    write_manifest(manifest, evidence_dir)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Family Office intelligence pipeline")
    sub = ap.add_subparsers(dest="stage", required=True)

    disc = sub.add_parser("discovery", help="discover + resolve + persist the candidate pool")
    disc.add_argument("--per-source", type=int, default=50,
                      help="fallback cap for any source without an explicit limit")
    disc.add_argument("--evidence-dir", default="docs/evidence")

    args = ap.parse_args()
    if args.stage == "discovery":
        report = run_discovery(args.per_source, args.evidence_dir)
        printable = dict(report)
        printable["resolution"] = {k: v for k, v in report["resolution"].items()
                                   if k != "multi_source_firms"}
        print(json.dumps(printable, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
