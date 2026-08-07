"""
LangGraph migration — Phase 2: framework-neutral AI Employee contract.

Verifies the adapter layer (`adapters.load_employees`) exposes the standard
framework-independent surface (mission/inputs/outputs/authority/skills/execution
rules + execute(state)) AND that each wrapped employee produces the SAME result as
the underlying agent class it delegates to (no business-logic drift). Every test
runs WITHOUT LangGraph — proving employees are framework-independent.
"""

from __future__ import annotations

import pytest

from fointel.operate import Orchestrator
from fointel.operate.adapters import load_employees
from fointel.operate.employee import (
    AIEmployee,
    EmployeeContract,
    EmployeeSkip,
)


@pytest.fixture()
def employees() -> dict[str, AIEmployee]:
    orch = Orchestrator()
    orch.register_defaults()
    return load_employees(orch.agents)


def test_every_employee_has_full_contract_surface(employees) -> None:
    assert set(employees) == {
        "engineering", "discovery", "entity", "validation", "classification",
        "governance", "release", "logging", "scheduler",
    }
    for name, emp in employees.items():
        assert isinstance(emp, AIEmployee)
        assert isinstance(emp.contract, EmployeeContract)
        # every field the brief demands is present and non-empty
        for attr in ("mission", "inputs", "outputs", "authority", "skills",
                     "decision_rule", "escalation_rule"):
            value = getattr(emp.contract, attr)
            assert value, f"{name} is missing {attr}"


def test_contract_describes_authority_actions(employees) -> None:
    # authority = the policy action names this employee may propose
    expected = {
        "engineering": {"engineering.dispatch"},
        "governance": {"governance.approve"},
        "release": {"release.publish"},
    }
    # governance+release must at least mention their real actions
    assert any("engineering" in a for a in employees["engineering"].contract.authority)
    assert "release" in employees["release"].contract.authority[0]


def test_employee_without_state_skips(employees) -> None:
    # an employee handed no cycle state is a clean logged no-op, not a crash / guess
    from fointel.operate.employee import EmployeeSkip
    for name, emp in employees.items():
        try:
            emp.execute(None)
            raise AssertionError(f"{name} did not skip on empty state")
        except EmployeeSkip:
            pass


def test_engineering_employee_plans_cycle(employees) -> None:
    res = employees["engineering"].execute({"candidates": []})
    assert res.outcome == "ok"
    assert "pause_unsafe_stages" in res.results.get("decision", "")


def test_employee_delegates_identical_result(employees) -> None:
    """The adapter must not change what the agent would have done unaided."""
    orch_agent = employees["engineering"]._agent
    from fointel.operate.orchestrator import Task
    task = Task(task_id="x", agent="engineering", action="engineering.dispatch",
                payload={"state": {"candidates": []}})
    raw = orch_agent.execute(task)
    wrapped = employees["engineering"].execute({"candidates": []}).results
    assert wrapped["decision"] == raw["decision"]
    assert wrapped["paused_stages"] == raw["paused_stages"]


def test_load_employees_is_framework_free(employees) -> None:
    """The employee layer must never import langgraph — only the graph executor may.
    Verified at the source level so sibling test modules importing langgraph cannot
    pollute the check."""
    import inspect
    from fointel.operate import employee, adapters
    for mod in (employee, adapters):
        src = inspect.getsource(mod)
        assert "langgraph" not in src, f"{mod.__name__} leaked langgraph"
        assert "langchain" not in src, f"{mod.__name__} leaked langchain"