"""Scheduler agent runner — the operating window entry point (Eman Phase 1 Step 7).

Runs ONE complete autonomous operating cycle end to end:

    Scheduler Wake -> Engineering Judgment -> Discovery -> Entity Resolution
    -> Validation -> Classification -> Governance -> Release -> Logging
    -> Scheduler Sleep

Every step is gated by the Policy Engine, every decision and result is written to
a raw JSONL run trace under logs/operating/, and a human-review queue fills with
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
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
    print(f"human-review queue ({len(result['pending_review'])} pending):")
    for item in result["pending_review"]:
        print(f"  - [{item.get('id')}] {item.get('reason')}")
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="Autonomous operating-cycle runner")
    ap.add_argument("--simulate", action="store_true", default=True,
                    help="run without network discovery (quiet-window cycle)")
    ap.add_argument("--engine", choices=["langgraph", "orchestrator"], default=None,
                    help="override FOINTEL_ENGINE for this run")
    args = ap.parse_args()
    run_operating_cycle(simulate=args.simulate, engine=args.engine)


if __name__ == "__main__":
    main()