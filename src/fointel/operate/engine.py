"""
Operating-cycle driver (migration Phase 5) — the routing switch.

`FOINTEL_ENGINE` selects the execution engine for the full operating cycle:

    FOINTEL_ENGINE=langgraph   -> LangGraph StateGraph (default for CLI/cron)
    FOINTEL_ENGINE=orchestrator-> the legacy deterministic loop (rollback path)

BOTH engines run the SAME 9 AI Employees through the SAME Policy Engine, thread
the same cycle state, write the same JSONL run trace, and fill the same
human-review queue. The only difference is the executor. Flipping the env var is
the rollback: no code change, immediate revert to the pre-migration runtime.

All optional surfaces (APScheduler — none; a public runtime endpoint — NOT
authorized) are deliberately absent: this is launchable from CLI / cron only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .orchestrator import Orchestrator
from .policy_engine import ActionStatus


def select_engine() -> str:
    """'langgraph' (default) or 'orchestrator'."""
    return os.getenv("FOINTEL_ENGINE", "langgraph").strip().lower()


def run_operating_cycle(inputs: dict[str, Any] | None = None,
                        engine: str | None = None) -> dict[str, Any]:
    """Run one operating cycle with the selected engine and return a summary
    compatible with `Orchestrator.summary()` + the raw trace path.

    The Orchestrator is always constructed (it owns the agent registry, the
    Policy Engine, the JSONL trace and the cycle-state); the selected
    engine then drives those same agents.

    Every cycle is governed by a ResourceGuard at the OUTERMOST gate: the
    engine refuses to start a cycle whose input already violates the resource
    budget, and it refuses results whose threaded state would overflow. This
    wraps BOTH engines identically, so the guard is a single enforcement point
    no matter which executor is selected (Release-gate P0). A process-wide
    CycleLock also guarantees only one cycle writes a given trace at a time.
    """
    from .guard import CycleLock, ResourceGuard, ResourceLimitError

    engine = (engine or select_engine()).lower()
    inputs = dict(inputs or {})

    # Resource gate BEFORE any work: refuse an input that already overflows.
    pre_state = dict(inputs.get("state", {}))
    for k, v in inputs.items():
        if k not in ("state",):
            pre_state[k] = v
    ResourceGuard().check(pre_state)

    orch = Orchestrator()
    orch.register_defaults()

    lock = CycleLock()
    if not lock.acquire():
        raise ResourceLimitError(
            f"cannot start cycle {orch.run_id}: the cycle lock is held by another "
            "operating run (scheduler overlap guard)."
        )
    try:
        if engine == "langgraph":
            result = _run_langgraph_cycle(orch, inputs)
        elif engine == "orchestrator":
            result = orch.run_cycle(dict(inputs))
        else:
            raise ValueError(f"unknown FOINTEL_ENGINE {engine!r} "
                             "(expected 'langgraph' or 'orchestrator')")

        # Resource gate AFTER the cycle: threaded state must stay within budget.
        cycle_state = result.get("state", result.get("cycle", {})) or {}
        ResourceGuard().check(cycle_state)

        orch.dump_summary()
        return {
            "engine": engine,
            "state": cycle_state,
            "steps": result.get("steps", []),
            "summary": orch.summary(),
            "trace": str(orch.trace.path),
            "pending_review": _pending(orch),
        }
    finally:
        lock.release()


def _pending(orch) -> list[dict]:
    return [i.to_dict() for i in orch.policies.queue.pending()]


def _run_langgraph_cycle(orch: Orchestrator, inputs: dict[str, Any]) -> dict[str, Any]:
    """Drive the LangGraph path, then replay its auditable steps into the same
    JSONL trace and human-review queue the legacy loop uses, so consumers see an
    identical record regardless of engine."""
    from .adapters import load_employees
    from .graph import OperatingGraph

    employees = load_employees(orch.agents)
    graph = OperatingGraph(employees=employees, policies=orch.policies)
    out = graph.compile().invoke({"cycle": dict(inputs), "steps": []})

    cycle = out.get("cycle", {})
    for step in out.get("steps", []):
        name, outcome = step.get("name"), step.get("outcome")
        action = step.get("action", name)
        decision = step.get("decision", {})
        orch.trace.emit({"event": "task_done", "agent": name, "action": action,
                         "outcome": outcome,
                         "decision": decision.get("status"),
                         "reason": decision.get("reason"),
                         "result": step.get("results", {})})
        orch.actions_taken.append({"task_id": f"lg-{name}", "action": action,
                                   "status": outcome,
                                   "decision": decision.get("status")})
        if outcome in (ActionStatus.ESCALATE, ActionStatus.REFUSE):
            orch.policies.queue.add(
                item_id=f"lg-{name}", reason=decision.get("reason", outcome),
                suggested_action=f"human review of {action}",
                context={"action": action, "engine": "langgraph"})
    return {"state": cycle, "steps": out.get("steps", [])}


def engine_from_env(env: str | None = None) -> str:
    """Pure helper for tests: read the override or fall back to FOINTEL_ENGINE."""
    return (env or os.getenv("FOINTEL_ENGINE", "langgraph")).strip().lower()


__all__ = ["select_engine", "run_operating_cycle", "engine_from_env"]