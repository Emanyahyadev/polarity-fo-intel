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
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "services"))

MARKER_PATH = ROOT / "data" / ".cycle-marker.json"


def record_skipped_window(reason: str) -> None:
    """Log a skipped window through the EXISTING scheduler.skip_overlap action
    (Tier 1 autonomous), then exit cleanly — an active cycle is never duplicated."""
    from fointel.operate.orchestrator import Orchestrator

    orch = Orchestrator()
    orch.register_defaults()
    task = orch._submit(agent="scheduler", action="scheduler.skip_overlap",
                        payload={"operation": "skip_overlap", "reason": reason})
    orch.run_task(task)
    orch.dump_summary()
    print(f"WINDOW_SKIPPED: {reason}")
    print(f"trace: {orch.trace.path}")


def start_heartbeat(marker, interval_seconds: float = 30.0) -> tuple[threading.Thread, threading.Event]:
    """Daemon heartbeat so a legitimately long cycle is never judged stale."""
    stop = threading.Event()

    def _beat() -> None:
        while not stop.wait(interval_seconds):
            marker.heartbeat()

    t = threading.Thread(target=_beat, daemon=True, name="cycle-marker-heartbeat")
    t.start()
    return t, stop


def guard_operating_floor(mode: str, run_id: str,
                          stale_seconds: float = 300.0) -> tuple[bool, object | None]:
    """Gate EVERY operating entrypoint through the overlap marker.

    Returns (ok, marker_or_None). When another window is ACTIVE the entrypoint
    must skip (recorded via scheduler.skip_overlap) — never queue, never run a
    duplicate cycle side by side.
    """
    from fointel.operate.marker import CycleMarker

    marker = CycleMarker(MARKER_PATH, stale_after_seconds=stale_seconds)
    ok, reason = marker.try_acquire(run_id, mode=mode)
    if not ok:
        return False, None
    return True, marker


def _fresh_run_id() -> str:
    import uuid
    return (f"run-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}")


def _run_guarded(mode: str, fn, args) -> None:
    """Run `fn` under the operating-floor guard: acquire the marker, heartbeat
    it for the whole run, release in all exits; skip (never queue/duplicate)
    when another window holds the floor."""
    if args.no_overlap_guard:
        fn()
        return
    ok, marker = guard_operating_floor(mode, run_id=_fresh_run_id(),
                                       stale_seconds=args.overlap_stale)
    if not ok:
        record_skipped_window(f"{mode} window skipped by overlap guard")
        return
    beat, stop_beat = start_heartbeat(marker)
    try:
        fn()
    finally:
        stop_beat.set()
        marker.release()


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
    ap.add_argument("--overlap-stale", type=float, default=300.0,
                    help="seconds without a heartbeat before a cycle marker is "
                         "judged stale and taken over (default 300)")
    ap.add_argument("--no-overlap-guard", action="store_true", default=False,
                    help="skip the cross-process overlap guard (tests/overnight only)")
    args = ap.parse_args()

    if args.continuous and args.simulate:
        ap.error("--continuous and --simulate are mutually exclusive")

    from fointel.config import settings
    inputs = {"per_source_limit": args.per_source or settings.target_records,
              "max_build": args.max_build or None}

    if args.continuous:
        _run_guarded("continuous",
                     lambda: run_continuous(inputs, interval_min=args.interval,
                                            budget_hours=args.hours,
                                            target=args.target, engine=args.engine),
                     args)
        return

    if args.simulate:
        run_operating_cycle(simulate=True, inputs=inputs, engine=args.engine)
        return

    _run_guarded("cycle",
                 lambda: run_operating_cycle(simulate=False, inputs=inputs,
                                             engine=args.engine),
                 args)


if __name__ == "__main__":
    main()