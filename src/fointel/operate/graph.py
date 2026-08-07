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
from .policy_engine import ActionStatus, PolicyEngine


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

    Every node is POLICY-GATED: before its employee runs, the node consults the
    Policy Engine for the action, and if the engine marks it ESCALATE or REFUSE the
    employee is NOT run — the step is recorded and the cycle halts at that node
    (conditional edge routes to END). The graph never bypasses the Policy Engine.
    """

    def __init__(self, employees: dict[str, AIEmployee], order: list[str] | None = None,
                 policies: PolicyEngine | None = None) -> None:
        self.employees = employees
        self.order = order or ROLE_ORDER
        self.policies = policies or PolicyEngine()
        self.graph = self._build()

    def _node(self, name: str):
        emp = self.employees[name]
        action_for_role = emp.contract.authority[0] if emp.contract.authority else name

        def run(state: _State) -> _State:
            cycle = state.get("cycle", {})
            # POLICY GATE — the engine is the sole authority. Consulted before work.
            decision = self.policies.decide(action_for_role, {})
            d = decision.to_dict()
            d.pop("at", None)          # trace timestamps already capture ts; keep tools deterministic
            step = {"name": name, "action": action_for_role,
                    "decision": d, "outcome": "queued",
                    "results": {}}
            if not decision.is_autonomous():
                # engine refused or escalated: do NOT run the employee.
                step["outcome"] = decision.status  # 'refuse' | 'escalate'
                cycle.setdefault("escalated", [])
                cycle["escalated"].append({"action": action_for_role,
                                           "reason": decision.reason})
                steps = list(state.get("steps", [])) + [step]
                return {"cycle": cycle, "steps": steps}
            # engine approved: run the employee (delegation only).
            outcome = _run_employee(emp, cycle)
            step["outcome"] = outcome.get("outcome", "ok")
            step["results"] = outcome.get("results", {})
            steps = list(state.get("steps", [])) + [step]
            return {"cycle": cycle, "steps": steps}

        run.__name__ = f"node_{name}"
        return run

    def _router(self, next_role: str | None):
        """After a node, continue to the next role UNLESS the policy gate halted
        the cycle (refuse/escalate) — then route to END. Control never continues
        past an action the Policy Engine did not approve."""

        def route(state: _State) -> str:
            steps = state.get("steps", [])
            last = steps[-1] if steps else {}
            if last.get("outcome") in ("refuse", "escalate"):
                return END
            return next_role if next_role else END

        route.__name__ = f"route_after"
        return route

    def _build(self) -> StateGraph:
        g = StateGraph(_State)
        for name in self.order:
            if name not in self.employees:
                raise KeyError(f"no employee registered for graph node {name!r}")
            g.add_node(name, self._node(name))
        for i in range(len(self.order) - 1):
            g.add_conditional_edges(self.order[i], self._router(self.order[i + 1]),
                                    {self.order[i + 1]: self.order[i + 1], END: END})
        g.add_edge(START, self.order[0])
        g.add_edge(self.order[-1], END)
        return g

    def compile(self, checkpointer=None):
        """Return the runnable, optionally-checkpointed compiled graph."""
        return self.graph.compile(checkpointer=checkpointer)


def build_operating_graph(agents: dict[str, AIEmployee],
                          order: list[str] | None = None,
                          policies: PolicyEngine | None = None) -> OperatingGraph:
    return OperatingGraph(employees=agents, order=order, policies=policies)


def run_cycle(inputs: dict[str, Any] | None = None,
              agents: dict[str, AIEmployee] | None = None,
              checkpointer=None,
              policies: PolicyEngine | None = None) -> dict[str, Any]:
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
    graph = OperatingGraph(employees=agents, policies=policies)
    compiled = graph.compile(checkpointer=checkpointer)
    result = compiled.invoke({"cycle": dict(inputs), "steps": []})
    return {"cycle": result.get("cycle", {}), "steps": result.get("steps", [])}


__all__ = ["OperatingGraph", "build_operating_graph", "run_cycle",
           "ROLE_ORDER", "CycleState"]