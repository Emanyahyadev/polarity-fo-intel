"""
LangGraph migration — Phase 4: Policy Engine connected into the graph.

The Policy Engine is the SINGLE authority. Every graph node consults it before
running; an action the engine refuses or escalates MUST NOT run and the cycle
must short-circuit (route to END), never continue to later autonomous stages.

All 9 realized roles are Tier-1 autonomous (happy path unaffected); a synthetic
role whose proposed action the engine does not approve must halt the graph.
"""

from __future__ import annotations

import pytest

from fointel.operate import Orchestrator
from fointel.operate.adapters import load_employees
from fointel.operate.employee import EmployeeContract, EmployeeResult
from fointel.operate.graph import OperatingGraph
from fointel.operate.policy_engine import ActionStatus

EMPTY_INPUTS = {"sources": [], "per_source_limit": 0}
CYCLE_ORDER = ["scheduler", "engineering", "discovery", "entity",
               "duplicate", "enrichment", "validation", "classification",
               "governance", "release", "embedding", "freshness", "monitoring",
               "logging"]


@pytest.fixture()
def graph():
    orch = Orchestrator()
    orch.register_defaults()
    return OperatingGraph(employees=load_employees(orch.agents))


def test_every_step_records_policy_decision(graph) -> None:
    compiled = graph.compile()
    out = compiled.invoke({"cycle": dict(EMPTY_INPUTS), "steps": []})
    for step in out["steps"]:
        # every node consulted the Policy Engine and recorded its decision
        assert "decision" in step
        assert step["decision"]["status"] == ActionStatus.AUTONOMOUS
        assert step["decision"]["tier"] == 1
        assert step["outcome"] not in ("refuse", "escalate")


def test_happy_path_runs_all_roles(graph) -> None:
    compiled = graph.compile()
    out = compiled.invoke({"cycle": dict(EMPTY_INPUTS), "steps": []})
    assert [s["name"] for s in out["steps"]] == CYCLE_ORDER


def test_unknown_action_halts_cycle_not_runs() -> None:
    """An employee whose announced action is not autonomous must NOT run; the
    graph stops at that node and never reaches later stages."""
    from fointel.operate.adapters import EngineeringEmployee

    orch = Orchestrator()
    orch.register_defaults()
    employees = dict(load_employees(orch.agents))

    # a role that announces an action the engine does not approve (unknown -> escalate)
    rogue = EngineeringEmployee.__new__(EngineeringEmployee)
    rogue.name = "rogue"
    rogue.contract = EmployeeContract(mission="rogue", inputs=(), outputs=(),
                                      authority=("rogue.act",), skills=(),
                                      decision_rule="", escalation_rule="")
    rogue._agent = orch.agents["engineering"]
    employees["rogue"] = rogue

    # begin the cycle with the rogue node, discovery next
    order = ["scheduler", "rogue", "discovery"]
    g = OperatingGraph(employees=employees, order=order)
    out = g.compile().invoke({"cycle": dict(EMPTY_INPUTS), "steps": []})
    # the rogue node recorded an escalate decision and the cycle stopped short
    assert out["steps"][-1]["outcome"] == "escalate"
    assert out["steps"][-1]["name"] == "rogue"
    step_names = [s["name"] for s in out["steps"]]
    assert "discovery" not in step_names  # halted, did not continue