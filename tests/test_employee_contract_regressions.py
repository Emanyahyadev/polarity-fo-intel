"""
Cycle: real-input contract regressions for the operating-layer AI Employees.

The empty-window tests prove the cycle never crashes and never invents work, but
they also mask two defects that only appear when a cycle is driven with REAL
(populated) input:

  * entity: `EntityResolver.resolve` requires typed `Candidate` objects. A raw
    dict candidate raised `AttributeError: 'dict' object has no attribute 'raw'`,
    so the entity agent FAILED on any real candidate pool.
  * validation: the orchestrator's single-record ValidationAgent shadowed the
    cycle's list-processing agent (registered first, so `validation` resolved to
    the wrong class) and returned `{'status': 'noop'}` for a list — the
    `{validated, passed, failures}` outputs the contract requires were never made.

These tests bind the registry and the real-input behaviour so the two cannot
regress. They exercise the Employee adapter surface (framework-independent) and
do NOT drive the network discovery harvest.
"""

from __future__ import annotations

from fointel.operate import Orchestrator
from fointel.operate.adapters import load_employees

# A raw-dict candidate exactly as the cycle would thread it from discovery.
RAW_CANDIDATE = {
    "fo_id": "FO-1",
    "name": "Cascade Family Office",
    "hq_city": "New York",
    "hq_state": "NY",
    "source": "curated",
}


def _employees() -> dict:
    orch = Orchestrator()
    orch.register_defaults()
    return load_employees(orch.agents)


def test_validation_binds_to_cycle_list_agent_not_orchestrator() -> None:
    """`validation` must resolve to the cycle's list-processing agent."""
    from fointel.operate.cycle import ValidationAgent
    orch = Orchestrator()
    orch.register_defaults()
    assert isinstance(orch.agents["validation"], ValidationAgent)


def test_entity_succeeds_on_raw_dict_candidate() -> None:
    """A raw dict candidate must resolve (typed Candidate coercion), not crash."""
    result = _employees()["entity"].execute({"candidates": [RAW_CANDIDATE]})
    assert result.outcome == "ok"
    assert isinstance(result.results["decisions"], list)
    assert result.results["resolved"] == 1


def test_validation_produces_contract_outputs_on_real_input() -> None:
    """validation must emit {validated, passed, failures} over a candidate list,
    honestly flagging a record that lacks required fields — not a quiet noop."""
    result = _employees()["validation"].execute({"candidates": [RAW_CANDIDATE]})
    assert result.outcome == "ok"
    assert "validated" in result.results
    assert result.results["passed"] == 0  # raw slot missing required gates


def test_governance_accepts_classifier_confidence_label() -> None:
    """classification emits `Confidence` string labels (High/Medium/Low); the
    policy gate must interpret them instead of crashing on float('Low')."""
    result = _employees()["governance"].execute({
        "classified": [
            {"name": "Cascade", "fo_type": "Multi-Family Office",
             "confidence": "High", "evident": True},
            {"name": "LowSignal", "fo_type": "Undetermined",
             "confidence": "Low", "evident": False},
        ]})
    assert result.outcome == "ok"
    by_name = {d["name"]: d for d in result.results["decisions"]}
    assert by_name["Cascade"]["action"] == "approve"
    assert by_name["LowSignal"]["action"] == "escalate"


def test_governance_accepts_numeric_confidence() -> None:
    """the numeric forms (0..1 and 0..100) already used by the policy engine
    must keep working through the same gate."""
    result = _employees()["governance"].execute({
        "classified": [
            {"name": "A", "fo_type": "Single-Family Office", "confidence": 0.95},
            {"name": "B", "fo_type": "Single-Family Office", "confidence": 60.0},
        ]})
    assert result.outcome == "ok"
    by_name = {d["name"]: d for d in result.results["decisions"]}
    assert by_name["A"]["action"] == "approve"
    assert by_name["B"]["action"] == "escalate"  # 60/100 = 0.60 < 0.85
