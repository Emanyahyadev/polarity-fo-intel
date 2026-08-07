"""
LangGraph StateGraph orchestration — the EXECUTION ENGINE (migration Phase 3).

Design contract (Eman's approval):
  * LangGraph is NOT the business logic — it is only the execution engine.
  * Every node's body calls an existing AI Employee (from `adapters.load_employees`)
    via the framework-neutral `execute(state)`. No business rule, no policy decision,
    no compute lives in this file.
  * The Policy Engine remains the single authority; node bodies + graph edges
    consult `decide()` only for routing (proceed / escalate / refuse) — they never
    decide themselves.

State: a plain serialisable dict (`CycleState` keys), so it is checkpointer-friendly
(Phase 6) and identical across drivers (legacy Orchestrator vs LangGraph).

All 9 realized employees are wired in the canonical cycle order:
    scheduler.wake -> engineering -> discovery -> entity -> validation ->
    classification -> governance -> release -> logging -> scheduler.sleep
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .adapters import load_employees
from .employee import AIEmployee, EmployeeSkip


class CycleState(TypedDict, total=False):
    """The threaded working state (documentation only; plain dict at runtime)."""
    candidates: list[Any]
    resolved: list[Any]
    validated: list[Any]
    classified: list[Any]
    decisions: list[Any]
    approved: list[Any]
    quarantined: list[Any]
    escalated: list[Any]
    errors: list[Any]
    metrics: dict[str, Any]
    steps: list[dict[str, Any]]   # audit trail of executed steps (name, outcome)


class _State(TypedDict, total=False):
    """LangGraph channel type: the cycle state plus an audit trail."""
    cycle: dict[str, Any]
    steps: list[dict[str, Any]]


def _run_employee(emp: AIEmployee, state: dict[str, Any]) -> dict[str, Any]:
    """Drive one employee; a normal empty-window skip is recorded, never a crash."""
    try:
        result = emp.execute(state)
        return result.to_dict()
    except EmployeeSkip:
        return {"outcome": "skipped", "results": {}, "notes": []}


ROLE_ORDER = ["scheduler", "engineering", "discovery", "entity",
              "validation", "classification", "governance", "release",
              "logging"]


class OperatingGraph:
    """A LangGraph StateGraph whose nodes are framework-neutral AI Employees.

    Build once with the employee registry produced from a real Orchestrator's
    agents. `compile()` returns the runnable graph (add checkpointing in Phase 6).
    """

    def __init__(self, employees: dict[str, AIEmployee], order: list[str] | None = None) -> None:
        self.employees = employees
        self.order = order or ROLE_ORDER
        self.graph = self._build()

    def _node(self, name: str):
        emp = self.employees[name]

        def run(state: _State) -> _State:
            cycle = state.get("cycle", {})
            step = {"name": name, "outcome": "queued"}
            outcome = _run_employee(emp, cycle)
            step["outcome"] = outcome.get("outcome", "ok")
            step["results"] = outcome.get("results", {})
            steps = list(state.get("steps", [])) + [step]
            return {"cycle": cycle, "steps": steps}

        run.__name__ = f"node_{name}"
        return run

    def _build(self) -> StateGraph:
        g = StateGraph(_State)
        for name in self.order:
            if name not in self.employees:
                raise KeyError(f"no employee registered for graph node {name!r}")
            g.add_node(name, self._node(name))
        for i in range(len(self.order) - 1):
            g.add_edge(self.order[i], self.order[i + 1])
        g.add_edge(START, self.order[0])
        g.add_edge(self.order[-1], END)
        return g

    def compile(self, checkpointer=None):
        """Return the runnable, optionally-checkpointed compiled graph."""
        return self.graph.compile(checkpointer=checkpointer)


def build_operating_graph(agents: dict[str, AIEmployee],
                          order: list[str] | None = None) -> OperatingGraph:
    return OperatingGraph(employees=agents, order=order)


def run_cycle(inputs: dict[str, Any] | None = None,
              agents: dict[str, AIEmployee] | None = None,
              checkpointer=None) -> dict[str, Any]:
    """Run one full operating cycle through the graph.

    Mirrors `Orchestrator.run_cycle` semantics (see tests for A/B equivalence).
    `agents` may be injected (tests) or built from a fresh orchestrator registry.
    """
    from .orchestrator import Orchestrator

    if agents is None:
        orch = Orchestrator()
        orch.register_defaults()
        agents = load_employees(orch.agents)
    inputs = inputs or {}
    graph = OperatingGraph(employees=agents)
    compiled = graph.compile(checkpointer=checkpointer)
    result = compiled.invoke({"cycle": dict(inputs), "steps": []})
    return {"cycle": result.get("cycle", {}), "steps": result.get("steps", [])}


__all__ = ["OperatingGraph", "build_operating_graph", "run_cycle",
           "ROLE_ORDER", "CycleState"]