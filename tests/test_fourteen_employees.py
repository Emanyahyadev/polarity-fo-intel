"""Cycle 3: the 14 AI Employees now form the full operating cycle.

Every realized employee runs through the Policy Engine as a Tier-1 node in the
canonical mission order, records an auditable step, and never invents work on an
empty window. The 4 roles realized in this cycle (duplicate, enrichment,
freshness, monitoring) reuse existing deterministic business logic — they must
not crash and must emit structured results. Together with the embedding /
scheduler / engineering / release / validation / classification / governance /
logging roles the cycle is the full 14-engineer roster.
"""

from __future__ import annotations

import pytest

from fointel.operate import Orchestrator
from fointel.operate.adapters import load_employees
from fointel.operate.graph import ROLE_ORDER, OperatingGraph
from fointel.operate.policy_engine import ActionStatus

EMPTY_INPUTS = {"sources": [], "per_source_limit": 0}

MISSION_ORDER = [
    "scheduler", "engineering", "discovery", "entity",
    "duplicate", "enrichment", "validation", "classification",
    "governance", "release", "embedding", "freshness", "monitoring", "logging",
]


@pytest.fixture()
def graph():
    orch = Orchestrator()
    orch.register_defaults()
    return OperatingGraph(employees=load_employees(orch.agents))


def test_mission_order_is_full_cycle(graph) -> None:
    assert graph.order == MISSION_ORDER
    assert len(graph.order) == 14


def test_all_fourteen_run_and_produce_evidence(graph) -> None:
    out = graph.compile().invoke({"cycle": dict(EMPTY_INPUTS), "steps": []})
    step_names = [s["name"] for s in out["steps"]]
    assert step_names == MISSION_ORDER
    for s in out["steps"]:
        assert s["outcome"] != "failed"                 # no crash on empty window
        assert s["decision"]["status"] == ActionStatus.AUTONOMOUS
        assert s["decision"]["tier"] == 1
        assert "results" in s                            # auditable step payload


def test_new_roles_are_quiet_skips_not_guesses(graph) -> None:
    out = graph.compile().invoke({"cycle": dict(EMPTY_INPUTS), "steps": []})
    by_name = {s["name"]: s for s in out["steps"]}
    # duplicate/enrichment/freshness on an empty pool skip cleanly
    assert by_name["duplicate"]["outcome"] != "failed"
    assert by_name["enrichment"]["outcome"] != "failed"
    assert by_name["freshness"]["outcome"] != "failed"
    # monitoring emits a real, measured snapshot (no invented numbers)
    snap = by_name["monitoring"]["results"].get("snapshot", {})
    assert snap == {"candidates": 0, "resolved": 0, "records": 0, "approved": 0,
                    "quarantined": 0, "escalated": 0, "errors": 0}


def test_ab_equivalence_holds_with_fourteen_roles() -> None:
    """Legacy Orchestrator and LangGraph must still agree on the quiet outcome
    after extending the roster to 13 — only the executor differs."""
    orch = Orchestrator()
    orch.register_defaults()
    legacy = orch.run_cycle(dict(EMPTY_INPUTS))
    result = __import__("fointel.operate.graph", fromlist=["run_cycle"]).run_cycle(
        dict(EMPTY_INPUTS))
    assert legacy["state"].get("candidates", []) == result["cycle"].get("candidates", [])
    assert legacy["state"].get("approved", []) == result["cycle"].get("approved", [])
    assert not result["cycle"].get("errors", [])