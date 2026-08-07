"""
Concrete AI Employees — thin adapters over the EXISTING business logic.

(LangGraph migration Phase 2.)

Each employee in `EMPLOYEES` is a wrapper that exposes the framework-independent
`AIEmployee` surface (mission/inputs/outputs/authority/skills/decision/escalation/
execute(state)) while DELEGATING the actual work to the already-existing agent
classes (EngineeringAgent, EntityResolutionAgent, ValidationAgent, ...) and service
modules. NOTHING here re-implements business logic; it only maps the new uniform
interface onto the codebase that already exists. If LangGraph is removed later,
these employees still run through the legacy Orchestrator because they share the
same underlying agent objects.

Design contract (Eman's decisions):
  * Policy Engine remains the single authority. An employee proposes; the
    orchestrator/LangGraph consults `decide()` before acting. Employees do not
    auto-approve their own actions.
  * Empty-window no-ops are the default success; employees never invent candidates.
  * Every execute() returns EmployeeResult (skipped/ok/failed) + mutates state.
"""

from __future__ import annotations

from typing import Any

from .orchestrator import AgentBase, Task
from .employee import (
    AIEmployee,
    EmployeeContract,
    EmployeeResult,
    EmployeeSkip,
)


class _DelegatingEmployee:
    """Base adapter: contract + execute(state) that drives an existing AgentBase."""

    _agent: AgentBase
    name: str
    contract: EmployeeContract

    def execute(self, state: dict[str, Any]) -> EmployeeResult:
        # the adapter contract is execute(cycle_state); None or a non-dict is a
        # clean no-op, never a guess
        if not isinstance(state, dict):
            raise EmployeeSkip("no state provided")
        tasks = Task(task_id=f"emp-{self._agent.name}", agent=self._agent.name,
                     action=self.contract.authority[0],
                     payload={"state": state})
        try:
            out = self._agent.execute(tasks)
            return EmployeeResult(outcome="ok", results=out or {})
        except EmployeeSkip:
            raise
        except Exception as exc:  # noqa: BLE001
            return EmployeeResult(outcome="failed", results={},
                                  notes=[f"{self._agent.name}: {exc}"])


class EngineeringEmployee(_DelegatingEmployee):
    """Chief Engineer: inspects state, builds the ordered plan, pauses unsafe stages."""

    name = "engineering"
    contract = EmployeeContract(
        mission="Decide what runs this cycle, in what order, and pause when a "
                "precondition (e.g. empty candidate pool) would make a later stage "
                "unsafe or vacuous.",
        inputs=("cycle_state",),
        outputs=("plan", "paused_stages", "decision", "priority"),
        authority=("engineering.dispatch", "engineering.prioritize"),
        skills=("cycle-planning", "precondition-gating"),
        decision_rule="proceed if candidate pool non-empty, else pause_unsafe_stages",
        escalation_rule="never fabricate work on an empty pool; defer to governance",
    )

    def __init__(self, agents: AgentBase) -> None:
        self._agent = agents["engineering"]


class DiscoveryEmployee(_DelegatingEmployee):
    """Discover family offices (reuses harvest). Candidates enter the pool only."""

    name = "discovery"
    contract = EmployeeContract(
        mission="Discover candidate family offices from external sources; persist "
                "them to the candidate pool, never the production dataset.",
        inputs=("sources", "per_source_limit", "state"),
        outputs=("yielded", "persisted", "resolved_firms", "pool_size", "per_source"),
        authority=("discovery.search",),
        skills=("source-harvest", "evidence-collection"),
        decision_rule="run harvest over the configured sources; log zero-yield as normal",
        escalation_rule="one failed source must not sink the cycle; degrade to a logged gap",
    )

    def __init__(self, agents: AgentBase) -> None:
        self._agent = agents["discovery"]


class EntityResolutionEmployee(_DelegatingEmployee):
    name = "entity"
    contract = EmployeeContract(
        mission="Normalise names and resolve aliases/duplicates with affirmative "
                "evidence; emit every merge decision.",
        inputs=("candidates",),
        outputs=("resolved", "merges", "possible_duplicates", "decisions"),
        authority=("entity.resolve", "entity.merge_high_confidence_duplicate"),
        skills=("fuzzy-match", "evidence-resolution"),
        decision_rule="merge only with identifier/name+geo evidence",
        escalation_rule="ambiguous duplicates stay distinct and escalate, never merged",
    )

    def __init__(self, agents: AgentBase) -> None:
        self._agent = agents["entity"]


class ValidationEmployee(_DelegatingEmployee):
    name = "validation"
    contract = EmployeeContract(
        mission="Apply the release gates to each candidate; report pass/fail per record.",
        inputs=("candidates",),
        outputs=("validated", "passed", "failures"),
        authority=("validation.review",),
        skills=("release-gating",),
        decision_rule="pass only records that clear every release gate",
        escalation_rule="a gate failure escalates; never auto-promote a failing record",
    )

    def __init__(self, agents: AgentBase) -> None:
        self._agent = agents["validation"]


class ClassificationEmployee(_DelegatingEmployee):
    name = "classification"
    contract = EmployeeContract(
        mission="Classify an entity as SFO / MFO / Undetermined using affirmative "
                "evidence only.",
        inputs=("records",),
        outputs=("classified", "escalated_uncertain", "assigned"),
        authority=("classification.classify",),
        skills=("firm-type-classification",),
        decision_rule="assign a concrete type only when classify() qualifies",
        escalation_rule="undetermined or low evidence escalates for human review",
    )

    def __init__(self, agents: AgentBase) -> None:
        self._agent = agents["classification"]


class GovernanceEmployee(_DelegatingEmployee):
    name = "governance"
    contract = EmployeeContract(
        mission="Apply the Policy Engine confidence bands to every classified "
                "candidate: approve / quarantine / escalate.",
        inputs=("records",),
        outputs=("decisions", "approved", "to_release"),
        authority=("governance.release_decision",),
        skills=("policy-enforcement",),
        decision_rule="approve only on verified type + confidence >= 0.85",
        escalation_rule="undetermined or low confidence escalates; never auto-approve",
    )

    def __init__(self, agents: AgentBase) -> None:
        self._agent = agents["governance"]


class ReleaseEmployee(_DelegatingEmployee):
    name = "release"
    contract = EmployeeContract(
        mission="Publish ONLY governance-approved records into data/final via "
                "export_dataset, and version the release.",
        inputs=("decisions", "approved"),
        outputs=("published", "count", "note"),
        authority=("release.publish",),
        skills=("data-publishing",),
        decision_rule="release only records whose governance decision is approve",
        escalation_rule="release.publish is gated autonomous: unapproved never ships",
    )

    def __init__(self, agents: AgentBase) -> None:
        self._agent = agents["release"]


class LoggingEmployee(_DelegatingEmployee):
    name = "logging"
    contract = EmployeeContract(
        mission="Write structured cycle logs, metrics and audit trails.",
        inputs=("state", "kind", "content"),
        outputs=("logged",),
        authority=("logging.write",),
        skills=("structured-logging",),
        decision_rule="emit an event per business step",
        escalation_rule="n/a — passive recorder",
    )

    def __init__(self, agents: AgentBase) -> None:
        self._agent = agents["logging"]


class SchedulerEmployee(_DelegatingEmployee):
    name = "scheduler"
    contract = EmployeeContract(
        mission="Open/close the operating window and register the next schedule.",
        inputs=("operation",),
        outputs=("opened", "closed", "scheduled"),
        authority=("scheduler.wake", "scheduler.sleep"),
        skills=("time-gating",),
        decision_rule="proceed when in the operating window",
        escalation_rule="never publish; only opens/closes the window",
    )

    def __init__(self, agents: AgentBase) -> None:
        self._agent = agents["scheduler"]


# Factory: build the registry from an already-registered Orchestrator's agents.
def load_employees(agents: dict[str, AgentBase]) -> dict[str, AIEmployee]:
    registry = {
        "engineering": EngineeringEmployee,
        "discovery": DiscoveryEmployee,
        "entity": EntityResolutionEmployee,
        "validation": ValidationEmployee,
        "classification": ClassificationEmployee,
        "governance": GovernanceEmployee,
        "release": ReleaseEmployee,
        "logging": LoggingEmployee,
        "scheduler": SchedulerEmployee,
    }
    out: dict[str, AIEmployee] = {}
    for name, cls in registry.items():
        out[name] = cls(agents)
    return out


__all__ = ["AIEmployee", "EmployeeContract", "EmployeeResult", "EmployeeSkip",
           "load_employees", "EngineeringEmployee"]