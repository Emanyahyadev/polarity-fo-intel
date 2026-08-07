"""
Framework-neutral AI Employee interface (LangGraph migration Phase 2).

Purpose: decouple the ORCHESTRATION engine from the BUSINESS employees.

The migration's core principle (per Eman's approval):

    LangGraph is NOT the business logic. LangGraph is ONLY the execution engine.
    Business logic lives inside AI Employees, and every AI Employee must remain
    reusable and framework-independent — even if LangGraph is removed later.

To honour that, every employee presents ONE standard surface:

    Mission | Inputs | Outputs | Authority | Skills
    Decision Rule | Escalation Rule | execute(state)

`AIEmployee.execute(state)` is the ONLY method an orchestrator (LangGraph OR the
legacy Orchestrator) drives. No graph-specific type ever leaks into an employee.
State (`CycleState` as a plain dict) is the single threaded contract.

This module is the CONTRACT. `adapters.py` provides the concrete employees that
wrap the existing agent classes / service modules. Business logic is NOT moved
here — it stays where it already lives (agent classes + services).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class EmployeeContract:
    """The declarative identity of one AI Employee (the brief's standard surface)."""
    mission: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    authority: tuple[str, ...]        # policy action names this employee may propose
    skills: tuple[str, ...]
    decision_rule: str
    escalation_rule: str

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


@dataclass
class EmployeeResult:
    """Standardised wrapper every employee returns so orchestrators can reason
    uniformly about the outcome (success + policy decision handled by the
    orchestrator; employees only return the business payload here)."""
    outcome: str                       # "ok" | "skipped" | "escalated" | "failed"
    results: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"outcome": self.outcome, "results": self.results, "notes": self.notes}


class EmployeeSkip(Exception):
    """Raised by an employee to signal a normal, logged no-op (nothing to do in
    this cycle). Orchestrators catch this and record a deterministic 'skipped'
    outcome — they NEVER fabricate work or invent candidates on an empty window."""


@runtime_checkable
class AIEmployee(Protocol):
    """The framework-independent employee surface."""

    name: str
    contract: EmployeeContract

    def execute(self, state: dict[str, Any]) -> EmployeeResult:
        """Run this employee against the shared cycle state. Returns an
        EmployeeResult; mutates `state` in place. May raise EmployeeSkip for a
        normal empty-window no-op (never a guess or a fabricated result)."""
        ...