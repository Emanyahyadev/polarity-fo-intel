"""
Agent Orchestrator (Phase 1 Step 4) — the brain.

Eman's pipeline: Scheduler -> Engineering Judgment Agent -> Task Queue -> Agent
Execution -> Results -> Logs.

Design decisions:
  * The Orchestrator itself is DETERMINISTIC control flow (no model inside). The
    'agentic' part — what the model may decide — is bounded to the tools/actions
    that the Policy Engine marks autonomous. Everything else escalates or refuses.
  * Every task, decision, tool call, and outcome is written to a raw run trace
    (JSONL) so the operating window is fully replayable and inspectable.
  * Idempotency: each run carries a run_id; tasks carry task_ids; a replayed run
    cannot duplicate work that already recorded a terminal status.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .policy_engine import PolicyEngine, AuthorityDecision, ActionStatus


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Task:
    task_id: str
    agent: str                    # "scheduler" | "discovery" | "validation" | "logging" | ...
    action: str                   # policy action name, e.g. "discovery.search"
    payload: dict = field(default_factory=dict)
    status: str = "queued"        # queued | running | done | escalated | refused | failed
    decision: Optional[AuthorityDecision] = None
    result: Any = None
    created_at: str = field(default_factory=_now)
    finished_at: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.decision is not None:
            d["decision"] = self.decision.to_dict()
        return d


class RunTrace:
    """Raw, unedited, inspectable record of everything the system did."""

    def __init__(self, run_id: str, path: Path) -> None:
        self.run_id = run_id
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: dict) -> None:
        line = {"run_id": self.run_id, "ts": _now(), **event}
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")


class AgentBase:
    """An agent = a named role with an allowed action surface. The Policy Engine
    decides whether any specific action may run autonomously."""

    name = "base"

    def __init__(self, orchestrator: "Orchestrator") -> None:
        self.orchestrator = orchestrator

    def execute(self, task: Task) -> Any:
        raise NotImplementedError


class SchedulerAgent(AgentBase):
    """Tier 1: wake, schedule, retry transient, skip overlap. Never publishes."""

    name = "scheduler"

    def execute(self, task: Task) -> dict:
        action = task.payload.get("operation", "tick")
        if action == "wake":
            return {"woke": True, "cycle": "operating_window",
                    "note": "operating window opened"}
        if action == "schedule":
            return {"scheduled": task.payload.get("jobs", []),
                    "note": "next cron firing registers in the scheduler run history"}
        if action == "retry_transient":
            return {"retried": task.payload.get("task_ids", [])}
        if action == "skip_overlap":
            return {"skipped": task.payload.get("task_ids", []),
                    "reason": "a previous run is still active for the same window"}
        if action == "sleep":
            return {"slept": True, "cycle": "operating_window",
                    "note": "operating window closed"}
        return {"ticked": True}


class DiscoveryAgent(AgentBase):
    """Tier 1: search, collect candidates, retry. Candidates enter the pool, never
    the production dataset. Reuses the Stage 1 harvest pipeline."""

    name = "discovery"

    def execute(self, task: Task) -> dict:
        action = task.payload.get("operation", "search")
        if action == "retry":
            return {"retried": True, "of": task.payload.get("candidate_ids", [])}
        try:
            from ..discovery.harvest import harvest
            from ..store import get_repository
            repo = get_repository()
            sources = task.payload.get("sources")
            limit = int(task.payload.get("per_source_limit", 5))
            report = harvest(repo, per_source_limit=limit, sources=sources)
            state = task.payload.get("state")
            if state is not None:
                state.setdefault("candidates", [])
            return {"query": task.payload.get("query"),
                    "source": task.payload.get("source"),
                    "yielded": report.get("total_yielded", 0),
                    "persisted": report.get("unique_added", 0),
                    "resolved_firms": report.get("resolved_firms", 0),
                    "pool_size": report.get("pool_size", 0),
                    "per_source": report.get("per_source", {})}
        except Exception as exc:  # noqa: BLE001 — one failed source must not sink the cycle
            state = task.payload.get("state")
            if state is not None:
                state.setdefault("errors", []).append(f"discovery: {exc}")
            return {"status": "failed", "error": str(exc), "yielded": 0}


class LoggingAgent(AgentBase):
    """Tier 1: write logs, reports, metrics, audit trails."""

    name = "logging"

    def execute(self, task: Task) -> dict:
        kind = task.payload.get("kind", "log")
        self.orchestrator.trace.emit({
            "event": "log", "kind": kind,
            "content": task.payload.get("content"),
        })
        return {"logged": kind}


# --------------------------------------------------------------------------- #

class Orchestrator:
    """Deterministic brain. Routes every task through Policy Engine -> agent."""

    def __init__(self, policies: Optional[PolicyEngine] = None,
                 logs_dir: Optional[Path] = None) -> None:
        self.policies = policies or PolicyEngine()
        self.logs_dir = Path(logs_dir or Path.cwd() / "logs" / "operating")
        self.run_id = f"run-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
        self.trace = RunTrace(self.run_id, self.logs_dir / f"{self.run_id}.jsonl")
        self.agents: dict[str, AgentBase] = {}
        self.registry: list[Task] = []
        self._done_ids: set[str] = set()   # idempotency guard
        self.actions_taken: list[dict] = []

    def register(self, agent: AgentBase) -> None:
        self.agents[agent.name] = agent

    def register_defaults(self) -> None:
        self.register(SchedulerAgent(self))
        self.register(DiscoveryAgent(self))
        self.register(LoggingAgent(self))
        self.register_cycle_agents()

    def register_cycle_agents(self) -> None:
        """Register the full operating-cycle roster (Engineering, Entity,
        Classification, Governance, Release). Idempotent on existing agents."""
        from .cycle import register_cycle_agents as _reg
        _reg(self)

    def _submit(self, agent: str, action: str, payload: dict | None = None) -> Task:
        task = Task(task_id=f"{self.run_id}-{agent}-{len(self.registry)}",
                    agent=agent, action=action, payload=payload or {})
        self.registry.append(task)
        return task

    def run_task(self, task: Task) -> Task:
        """Run one task through the full authority gate. Control flow enforces what
        may run; a refused/escalated task never reaches an agent that publishes."""
        # idempotency: never re-execute a terminal task
        if task.task_id in self._done_ids:
            self.trace.emit({"event": "skip_duplicate", "task_id": task.task_id})
            return task
        decision = self.policies.decide(task.action, task.payload)
        task.decision = decision
        if decision.status == ActionStatus.REFUSE:
            task.status = "refused"
            self.trace.emit({"event": "refused", "task_id": task.task_id,
                             "action": task.action, "reason": decision.reason})
            return task
        if decision.status == ActionStatus.ESCALATE:
            task.status = "escalated"
            self.policies.queue.add(
                item_id=task.task_id, reason=decision.reason,
                suggested_action=f"human review of {task.action}",
                context={"action": task.action, "payload": task.payload})
            self.trace.emit({"event": "escalated", "task_id": task.task_id,
                             "action": task.action, "reason": decision.reason,
                             "queue_item": task.task_id})
            return task

        # autonomous
        agent = self.agents.get(task.agent)
        if agent is None:
            task.status = "failed"
            self.trace.emit({"event": "failed", "task_id": task.task_id,
                             "reason": f"no agent named {task.agent}"})
            return task
        task.status = "running"
        self.trace.emit({"event": "task_start", "task_id": task.task_id,
                         "agent": task.agent, "action": task.action,
                         "payload": task.payload})
        try:
            task.result = agent.execute(task)
            task.status = "done"
            self.trace.emit({"event": "task_done", "task_id": task.task_id,
                             "result": task.result})
        except Exception as exc:  # noqa: BLE001 — the run must survive agent failures
            task.status = "failed"
            self.trace.emit({"event": "task_failed", "task_id": task.task_id,
                             "error": str(exc), "error_type": type(exc).__name__})
        finally:
            task.finished_at = _now()
            self._done_ids.add(task.task_id)
            self.actions_taken.append({"task_id": task.task_id, "action": task.action,
                                       "status": task.status,
                                       "decision": decision.status})
        return task

    def plan(self, jobs: list[dict]) -> list[Task]:
        """Scheduler-style: enqueue a list of {agent, action, payload} and run them."""
        tasks = [self._submit(job["agent"], job["action"], job.get("payload")) for job in jobs]
        for t in tasks:
            self.run_task(t)
        return tasks

    def summary(self) -> dict:
        statuses: dict[str, int] = {}
        for t in self.registry:
            statuses[t.status] = statuses.get(t.status, 0) + 1
        return {
            "run_id": self.run_id,
            "tasks": len(self.registry),
            "statuses": statuses,
            "escalated_to_human_review": len(self.policies.queue.pending()),
            "trace_file": str(self.trace.path),
            "actions": self.actions_taken,
        }

    def dump_summary(self, path: Optional[Path] = None) -> Path:
        path = path or (self.logs_dir / f"{self.run_id}-summary.json")
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.summary(), fh, indent=2, default=str)
        return path

    # ---------------------------------------------------------------------- #
    # Full operating cycle (wake -> ... -> sleep)
    # ---------------------------------------------------------------------- #
    def run_cycle(self, inputs: Optional[dict] = None) -> dict:
        """Run one complete autonomous operating cycle and thread a CycleState.

        Sequence: scheduler.wake -> engineering -> discovery -> entity ->
        validation -> classification -> governance -> release -> scheduler.sleep.
        Returns the final cycle state + a per-step action trace. Safe to run on
        an empty window (stages with no input skip or escalate; the cycle never
        invents candidates)."""
        inputs = inputs or {}
        # wake
        self.run_task(self._submit(agent="scheduler", action="scheduler.wake",
                                   payload={"operation": "wake", **inputs}))
        state: dict = dict(inputs.get("state", {}))
        jobs = [
            {"agent": "engineering", "action": "engineering.dispatch",
             "payload": {"state": state}},
            {"agent": "discovery", "action": "discovery.search",
             "payload": {"state": state,
                         "sources": inputs.get("sources"),
                         "per_source_limit": inputs.get("per_source_limit", 5)}},
            {"agent": "entity", "action": "entity.resolve",
             "payload": {"state": state, "candidates": state.get("candidates", [])}},
            {"agent": "duplicate", "action": "duplicate.detect",
             "payload": {"state": state, "records": state.get("resolved", [])}},
            {"agent": "enrichment", "action": "enrichment.fetch",
             "payload": {"state": state, "candidates": state.get("candidates", [])}},
            {"agent": "validation", "action": "validation.review",
             "payload": {"state": state, "candidates": state.get("resolved", [])}},
            {"agent": "classification", "action": "classification.classify",
             "payload": {"state": state, "records": state.get("validated", [])}},
            {"agent": "governance", "action": "governance.release_decision",
             "payload": {"state": state, "records": state.get("classified", [])}},
            {"agent": "release", "action": "release.publish",
             "payload": {"state": state, "decisions": state.get("decisions", []),
                         "out_dir": inputs.get("out_dir", "data/final")}},
            {"agent": "embedding", "action": "embedding.update",
             "payload": {"state": state,
                         "out_dir": inputs.get("out_dir", "data/final")}},
            {"agent": "freshness", "action": "freshness.detect_stale",
             "payload": {"state": state, "records": state.get("approved", [])}},
            {"agent": "monitoring", "action": "monitoring.check_health",
             "payload": {"state": state, "emit": True}},
            {"agent": "logging", "action": "logging.write",
             "payload": {"state": state, "kind": "cycle_report",
                         "content": json.dumps(state, default=str)}},
        ]
        self.plan(jobs)
        # sleep
        self.run_task(self._submit(agent="scheduler", action="scheduler.sleep",
                                   payload={"operation": "sleep", "state": state}))
        return {"state": state, "actions": self.actions_taken,
                "summary": self.summary()}