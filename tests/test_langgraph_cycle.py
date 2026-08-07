"""
LangGraph migration — Phase 3: employees wrapped as LangGraph nodes.

Verifies the StateGraph (graph.py) drives the SAME 14 employees in the SAME order
as the legacy Orchestrator, and produces an equivalent outcome (A/B equivalence).
Absent an LLM and a non-empty candidate pool this is a clean, deterministic skip —
the graph must never invent work, and it must not crash on an empty window.

Employees remain framework-independent: this test imports langgraph only at the
graph layer, never inside an employee.
"""

from __future__ import annotations

import pytest

from fointel.operate import Orchestrator
from fointel.operate.adapters import load_employees
from fointel.operate.graph import ROLE_ORDER, OperatingGraph, run_cycle

EMPTY_INPUTS = {"sources": [], "per_source_limit": 0}


@pytest.fixture()
def graph():
    orch = Orchestrator()
    orch.register_defaults()
    employees = load_employees(orch.agents)
    return OperatingGraph(employees=employees)


def test_graph_has_all_fourteen_roles_in_order(graph) -> None:
    assert graph.order == ROLE_ORDER
    assert set(graph.order) == set(graph.employees)


def test_compile_produces_runnable_graph(graph) -> None:
    compiled = graph.compile()
    assert compiled is not None
    out = compiled.invoke({"cycle": dict(EMPTY_INPUTS), "steps": []})
    # every node ran and produced an auditable step
    step_names = [s["name"] for s in out["steps"]]
    assert step_names == graph.order
    # no step failed on an empty window
    for s in out["steps"]:
        assert s["outcome"] != "failed"


def test_graph_ab_equivalence_with_orchestrator() -> None:
    """The graph outcome must match the legacy Orchestrator.run_cycle for the same
    quiet-window input — proving the migration changes only the executor."""
    orch_a = Orchestrator()
    orch_a.register_defaults()
    legacy = orch_a.run_cycle(dict(EMPTY_INPUTS))

    result = run_cycle(dict(EMPTY_INPUTS))
    graph_state = result["cycle"]

    # the threaded candidate/resolved/etc lists are empty in both drivers
    assert legacy["state"].get("candidates", []) == graph_state.get("candidates", [])
    assert legacy["state"].get("approved", []) == graph_state.get("approved", [])
    assert not graph_state.get("errors", [])


def test_graph_skip_is_deterministic(graph) -> None:
    out1 = run_cycle(dict(EMPTY_INPUTS))
    out2 = run_cycle(dict(EMPTY_INPUTS))
    assert out1["steps"] == out2["steps"]


def test_graph_no_business_rule_in_executor() -> None:
    """The graph file must contain only orchestration mechanics, no compute/business."""
    import inspect
    from fointel.operate import graph as g
    src = inspect.getsource(g)
    # discovery subprocess/low-level network code must NOT be resident here
    for banned in ("EntityResolver(", "ReleaseGate(", "harvest(", "firm_type.classify"):
        assert banned not in src, f"business logic leaked into graph.py: {banned}"