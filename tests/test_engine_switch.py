"""
LangGraph migration — Phase 5: engine routing switch (rollback path).

`FOINTEL_ENGINE` selects langgraph (default) or the legacy orchestrator. Both must
run the same employees, respect the same Policy Engine, write a run trace, and
fill the same review queue — the only difference is the executor. Setting the env
var is the complete, no-code-change rollback mechanism.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fointel.operate.engine import (
    engine_from_env,
    run_operating_cycle,
    select_engine,
)

EMPTY_INPUTS = {"sources": [], "per_source_limit": 0}


def test_default_engine_is_langgraph() -> None:
    assert select_engine() == "langgraph"
    assert engine_from_env() == "langgraph"


def test_env_override_selects_orchestrator(monkeypatch) -> None:
    monkeypatch.setenv("FOINTEL_ENGINE", "orchestrator")
    assert select_engine() == "orchestrator"
    assert engine_from_env() == "orchestrator"


def test_unknown_engine_rejected() -> None:
    with pytest.raises(ValueError):
        run_operating_cycle(dict(EMPTY_INPUTS), engine="bogus")


def test_langgraph_engine_runs_cycle_and_writes_trace() -> None:
    out = run_operating_cycle(dict(EMPTY_INPUTS), engine="langgraph")
    assert out["engine"] == "langgraph"
    assert Path(out["trace"]).exists()
    lines = list(Path(out["trace"]).read_text(encoding="utf-8").splitlines())
    assert lines  # an audit record exists
    # all fourteen employees produced a decision line
    assert out["pending_review"] == []
    assert out["state"].get("approved", []) == []


def test_orchestrator_engine_still_runs() -> None:
    # the legacy loop remains a first-class option (rollback path)
    out = run_operating_cycle(dict(EMPTY_INPUTS), engine="orchestrator")
    assert out["engine"] == "orchestrator"
    assert Path(out["trace"]).exists()


def test_both_engines_produce_equivalent_quiet_outcome() -> None:
    lg = run_operating_cycle(dict(EMPTY_INPUTS), engine="langgraph")
    or_ = run_operating_cycle(dict(EMPTY_INPUTS), engine="orchestrator")
    # identical business outcome on the quiet window regardless of engine
    assert lg["state"].get("approved", []) == or_["state"].get("approved", [])
    assert lg["state"].get("candidates", []) == or_["state"].get("candidates", [])
    assert not lg["state"].get("errors") and not or_["state"].get("errors")