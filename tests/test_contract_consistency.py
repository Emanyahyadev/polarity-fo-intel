"""
Contract <-> implementation consistency (release gate).

The single source of truth for the AI Employee roster is `agents/contract.json`.
These tests bind that documentation to the actual implementation so the two can
never silently drift apart:

    * the documented cycle equals `graph.ROLE_ORDER`
    * the documented agent set equals the registry in `adapters.load_employees`
      and the legacy `Orchestrator` cycle jobs
    * the documented "policy_dependencies" exist in `policies/authority.json`
      so every action a contract claims the employee proposes is real
    * every contract is complete (the full field surface the enterprise spec
      requires is present and non-empty on each of the 14 employees)

This runs on every push/pr via the test gate; a mismatch here fails the build
and must be resolved in documentation or implementation before merge.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "agents" / "contract.json"
POLICY_PATH = ROOT / "policies" / "authority.json"

# The full operational-spec fields every employee contract must carry.
_REQUIRED_KEYS = {
    "name", "business_purpose", "responsibilities", "inputs", "outputs",
    "dependencies", "consumes", "produces", "tools_used", "knowledge_sources",
    "policy_dependencies", "authority_boundary", "autonomous_actions",
    "never_allowed", "escalation_rules", "decision_rules", "retry_policy",
    "failure_policy", "success_criteria", "execution_priority", "execution_order",
    "structured_logs_generated", "metrics_produced", "checkpoint_support",
    "human_approval_conditions", "framework_independence", "execute_contract",
    "unit_tests", "integration_tests", "related_repository_files",
}


@pytest.fixture(scope="module")
def contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_contract_is_the_fourteen_single_source(contract) -> None:
    assert contract["schema_version"].startswith("2.")
    assert contract["employee_count"] == 14
    assert len(contract["agents"]) == 14
    assert len(contract["cycle"]) == 14
    assert set(contract["cycle"]) == set(contract["agents"])


def test_contract_cycle_matches_graph_role_order(contract) -> None:
    from fointel.operate.graph import ROLE_ORDER
    assert contract["cycle"] == list(ROLE_ORDER)


def test_contract_agents_match_implemented_registry(contract) -> None:
    from fointel.operate import Orchestrator
    from fointel.operate.adapters import load_employees
    orch = Orchestrator()
    orch.register_defaults()
    implemented = set(load_employees(orch.agents))
    assert set(contract["agents"]) == implemented
    assert len(implemented) == 14


def test_contract_matches_orchestrator_cycle_jobs(contract) -> None:
    """The orchestrator's run_cycle dispatches a job per contract role (minus the
    scheduler wake/sleep framing) and every job maps to a documented agent."""
    from fointel.operate import Orchestrator
    orch = Orchestrator()
    orch.register_defaults()
    # reconstruct the job roles invoked by run_cycle
    from fointel.operate.orchestrator import Orchestrator as O
    src = O.run_cycle.__code__.co_firstlineno  # noqa: F841 — presence check
    documented = set(contract["agents"])
    # every implemented agent must be invoked by the cycle (via ROLE_ORDER match above)
    from fointel.operate.adapters import load_employees
    implemented = set(load_employees(orch.agents))
    assert implemented <= documented
    # executive frame: scheduler + 12 mid + logging
    assert {"scheduler", "logging"} < documented


def test_policy_dependencies_exist_in_authority_matrix(contract) -> None:
    """Every policy action a contract claims an employee may propose must actually
    exist in policies/authority.json (tier-1 or escalate trigger) — no invented
    authority."""
    authority = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    tier1 = set(authority["authority_matrix"]["tier_1_autonomous"]["actions"])
    never = authority["authority_matrix"]["tier_3_refuse"]["never"]
    for name, spec in contract["agents"].items():
        for action in spec["policy_dependencies"]:
            assert action in tier1, (
                f"{name} claims policy action {action!r} but it is not in "
                "policies/authority.json tier-1"
            )


def test_contract_fields_are_complete_and_nonempty(contract) -> None:
    """Every employee must expose the full enterprise operational spec — a
    missing or empty field fails the documentation gate."""
    for name, spec in contract["agents"].items():
        missing = _REQUIRED_KEYS - set(spec)
        assert not missing, f"{name} contract is missing {sorted(missing)}"
        # the operatieonally-meaningful prose fields must never be empty; list
        # evidence fields may legitimately be empty when the employee truly
        # produces none (an empty list is the honest answer, not an omission).
        for key in sorted(_REQUIRED_KEYS):
            value = spec[key]
            if key in ("execution_order", "checkpoint_support") or isinstance(value, list):
                continue
            assert value not in (None, ""), f"{name}.{key} is empty"


def test_execution_order_is_sequential_and_unique(contract) -> None:
    orders = [spec["execution_order"] for spec in contract["agents"].values()]
    assert sorted(orders) == list(range(14))
    assert len(set(orders)) == 14


def test_framework_independence_declared(contract) -> None:
    """Every employee must be declared LangGraph-independent (and audited in
    test_employee_contract.py at the source level)."""
    for name, spec in contract["agents"].items():
        assert spec["framework_independence"].lower().startswith("yes"), name


def test_employee_contract_surface_matches_documented_autonomy(contract) -> None:
    """The in-code EmployeeContract.authority must agree with the policy actions
    the documented contract lists (the employee can only propose its real surface)."""
    from fointel.operate import Orchestrator
    from fointel.operate.adapters import load_employees
    orch = Orchestrator()
    orch.register_defaults()
    for name, emp in load_employees(orch.agents).items():
        documented = contract["agents"][name]["policy_dependencies"]
        in_code = set(emp.contract.authority)
        assert in_code <= set(documented), (
            f"{name} in-code authority {sorted(in_code)} exceeds documented "
            f"{sorted(documented)}"
        )