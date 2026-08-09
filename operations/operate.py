"""Scheduler agent runner — the operating window entry point (Eman Phase 1 Step 7).

Runs ONE complete autonomous operating cycle end to end:

    Scheduler Wake -> Engineering Judgment -> Discovery -> Entity Resolution
    -> Validation -> Classification -> Governance -> Release -> Logging
    -> Scheduler Sleep

Every step is gated by the Policy Engine, every decision and result is written to
a raw JSONL run trace under logs/operating/, and a review queue fills with
anything the engine could not approve. Invoked by cron / GitHub Actions; each
invocation is one independent, idempotent run.

The execution engine is selected by FOINTEL_ENGINE (default: langgraph). Set
FOINTEL_ENGINE=orchestrator to run the legacy deterministic loop — the rollback
path. Both engines run the same employees, policy engine, trace and review queue.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "services"))


def run_operating_cycle(simulate: bool = True, inputs: dict | None = None,
                        engine: str | None = None) -> dict:
    from fointel.operate.engine import run_operating_cycle as drive

    # In simulate mode no network discovery runs; the cycle still exercises every
    # stage against the empty/quiet window and proves the loop is stable.
    cycle_inputs = dict(inputs or {})
    if simulate:
        cycle_inputs.setdefault("sources", [])
        cycle_inputs.setdefault("per_source_limit", 0)

    result = drive(cycle_inputs, engine=engine)
    print(json.dumps(result["summary"], indent=2, default=str))
    print(f"engine: {result['engine']}")
    print(f"trace: {result['trace']}")
    print(f"review queue ({len(result['pending_review'])} pending):")
    for item in result["pending_review"]:
        print(f"  - [{item.get('id')}] {item.get('reason')}")
    return result


def collect_progress() -> tuple[int, int]:
    """(total released records, verified contacts) in the canonical store right now."""
    from fointel.operate.continuous import contact_count
    from fointel.rag.load import load_records_from_store

    try:
        records = load_records_from_store()
        return len(records), contact_count(records)
    except Exception:
        return 0, 0


def run_continuous(inputs: dict, interval_min: float, budget_hours: float,
                   target: int, engine: str | None) -> None:
    """Re-wake the operating cycle until `target` verified contacts are released
    or the time budget is exhausted. Idempotent: each cycle merges into the
    canonical store (existing records win by fo_id), so re-discovery cannot
    duplicate. Progress is appended to logs/operating/continuous.jsonl."""
    from fointel.operate.continuous import planned_cycles

    log_path = ROOT / "logs" / "operating" / "continuous.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    total, verified = collect_progress()
    cycles = planned_cycles(budget_hours, interval_min, target, verified)
    print(f"continuous collect: target={target} verified contacts, budget={budget_hours}h, "
          f"interval={interval_min}min, planned cycles={cycles}, "
          f"current store={total} records / {verified} verified contacts")

    deadline = time.monotonic() + budget_hours * 3600.0
    with log_path.open("a", encoding="utf-8") as logf:
        logf.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                               "event": "start", "target": target,
                               "budget_hours": budget_hours,
                               "interval_min": interval_min,
                               "current_verified": verified,
                               "current_total": total}) + "\n")

    n_cycle = 0
    while True:
        n_cycle += 1
        print(f"[cycle {n_cycle}] waking the operating cycle ...")
        run_operating_cycle(simulate=False, inputs=inputs, engine=engine)

        total, verified = collect_progress()
        print(f"[cycle {n_cycle}] store now: {total} records, {verified} verified contacts")
        with log_path.open("a", encoding="utf-8") as logf:
            logf.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                                   "event": "cycle", "cycle": n_cycle,
                                   "verified": verified, "total": total,
                                   "target": target}) + "\n")

        if verified >= target:
            print(f"TARGET_REACHED: {verified} verified contacts (>= {target})")
            with log_path.open("a", encoding="utf-8") as logf:
                logf.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                                       "event": "done", "reason": "target",
                                       "verified": verified}) + "\n")
            return
        if time.monotonic() >= deadline:
            print(f"BUDGET_EXHAUSTED: {budget_hours}h elapsed with {verified} "
                  f"verified contacts (< {target})")
            with log_path.open("a", encoding="utf-8") as logf:
                logf.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(),
                                       "event": "done", "reason": "budget",
                                       "verified": verified}) + "\n")
            return
        print(f"[cycle {n_cycle}] sleeping {interval_min} minutes ...")
        time.sleep(interval_min * 60.0)


def main() -> None:
    ap = argparse.ArgumentParser(description="Autonomous operating-cycle runner")
    ap.add_argument("--simulate", action="store_true", default=False,
                    help="run without network discovery (quiet-window cycle)")
    ap.add_argument("--per-source", type=int, default=0,
                    help="real discovery cap per source (0 = settings.target_records)")
    ap.add_argument("--max-build", type=int, default=0,
                    help="cap how many discovered candidates the enrichment stage "
                         "builds this run (0 = uncapped)")
    ap.add_argument("--engine", choices=["langgraph", "orchestrator"], default=None,
                    help="override FOINTEL_ENGINE for this run")
    ap.add_argument("--continuous", action="store_true", default=False,
                    help="collect continuously: re-wake the cycle until --target "
                         "verified contacts are released or --hours elapse")
    ap.add_argument("--interval", type=float, default=60.0,
                    help="minutes between cycles in continuous mode (default 60)")
    ap.add_argument("--hours", type=float, default=48.0,
                    help="time budget in hours for continuous mode (default 48)")
    ap.add_argument("--target", type=int, default=700,
                    help="verified contacts to collect in continuous mode (default 700)")
    args = ap.parse_args()

    if args.continuous and args.simulate:
        ap.error("--continuous and --simulate are mutually exclusive")

    from fointel.config import settings
    inputs = {"per_source_limit": args.per_source or settings.target_records,
              "max_build": args.max_build or None}

    if args.continuous:
        run_continuous(inputs, interval_min=args.interval, budget_hours=args.hours,
                       target=args.target, engine=args.engine)
        return

    run_operating_cycle(simulate=args.simulate, inputs=inputs, engine=args.engine)


if __name__ == "__main__":
    main()