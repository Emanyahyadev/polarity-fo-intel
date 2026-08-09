"""
Cycle: discovery -> build -> gate -> release must END in the production dataset.

The scheduled cycle ("Wake the operating cycle") previously ran all 14 employees
but RELEASE only reported placeholder counts — it never wrote to `data/final`, so
the scheduled run found no offices and saved nothing to the CSV/RAG. These tests
bind the closed loop offline (no network):

  * discovery threads THIS run's harvested candidates into cycle state so
    downstream stages see real data (before they saw an empty window),
  * classification/g overnance never approve without affirmative evidence,
  * release merges approved records into the lossless store (`records.json`),
    never drops the curated store, and re-exports CSV/XLSX.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from fointel.operate import Orchestrator
from fointel.operate.adapters import load_employees
from fointel.schema import AuditEntry, Confidence, FamilyOfficeRecord, FOType, SourceClass

# An approved-quality record built like the enrichment stage would (evidence-backed):
# SFO, High classification confidence, one verification source, provenance on name.
AUM_TEXT = "$1.2B (SEC Form ADV Item 5.F total regulatory AUM)"


def _approved_record(fo_id: str, name: str) -> FamilyOfficeRecord:
    return FamilyOfficeRecord(
        fo_id=fo_id, name=name, fo_type=FOType.SFO,
        fo_type_evidence="firm self-identifies as a family office; SEC IAPD registration record",
        fo_type_confidence=Confidence.HIGH, hq_city="New York", hq_state="NY",
        hq_country="United States", estimated_aum=AUM_TEXT,
        discovery_source=SourceClass.SEC_IAPD,
        data_as_of=date(2026, 8, 1),
        record_confidence=Confidence.HIGH,
        verification_sources=[
            {"source_class": SourceClass.SEC_IAPD.value,
             "verifies": "firm registration, family-office status, type",
             "accessed_at": date(2026, 8, 1).isoformat()},
        ],
    )


@pytest.fixture()
def employees() -> dict:
    orch = Orchestrator()
    orch.register_defaults()
    return load_employees(orch.agents)


def test_discovery_threads_candidates_into_state(monkeypatch) -> None:
    """DiscoveryAgent must hand THIS run's harvested candidates to the cycle, not
    leave the window empty (the bug: downstream stages saw zero data every run)."""
    from fointel.discovery.base import Candidate
    from fointel.schema import SourceClass

    raw_fake = [
        Candidate(name="Cascade FO", source_class=SourceClass.DIRECTORY,
                  source_url="https://example/fo", raw={"name": "Cascade FO"}),
        Candidate(name="Riverbend Family Office", source_class=SourceClass.SEC_IAPD,
                  identifiers={"crd": "12345"}, raw={"crd": "12345"}),
    ]
    fake = {"total_yielded": 2, "unique_added": 2, "resolved_firms": 2, "pool_size": 50,
            "per_source": {"directory": {"yielded": 1}, "iapd": {"yielded": 1}},
            "resolution": {}, "candidates": [c.model_dump(mode="json") for c in raw_fake]}

    from fointel.operate.orchestrator import DiscoveryAgent

    # pack a fake harvest in place of the network call
    monkeypatch.setattr("fointel.discovery.harvest.harvest", lambda *a, **k: fake)
    orch = Orchestrator()
    orch.register_defaults()
    assert isinstance(orch.agents["discovery"], DiscoveryAgent)
    state: dict[str, object] = {}
    from fointel.operate.orchestrator import Task
    orch.agents["discovery"].execute(Task(task_id="t", agent="discovery",
                                          action="discovery.search",
                                          payload={"state": state, "sources": []}))
    cands = state["candidates"]
    assert len(cands) == 2
    assert cands[0]["name"] == "Cascade FO"
    assert cands[1]["identifiers"]["crd"] == "12345"
    assert state.get("errors", []) == []


def test_classification_escalates_type_without_evidence(employees) -> None:
    """A claim of 'Single-Family Office' with NO evidence must stay Undetermined
    and escalate — the classifier may never assign a type from a bare label."""
    res = employees["classification"].execute({"records": [
        {"name": "Fabricated FO", "fo_type": "Single-Family Office",
         "fo_type_evidence": None, "fo_type_confidence": "High"},
        {"name": "Proven FO", "fo_type": "Multi-Family Office",
         "fo_type_evidence": "SEC IAPD registration; firm website",
         "fo_type_confidence": "High"},
    ]}).results
    by_name = {c["name"]: c for c in res["classified"]}
    assert by_name["Fabricated FO"]["fo_type"] == "Undetermined"
    assert by_name["Fabricated FO"]["evident"] is False
    assert "Fabricated FO" in res["escalated_uncertain"]
    assert by_name["Proven FO"]["fo_type"] == "Multi-Family Office"


def test_gate_to_approve_to_release_writes_store_and_exports(employees, tmp_path: Path) -> None:
    """closed loop: an evidence-backed record -> classification -> governance
    approve -> release writes records.json + CSV + XLSX (exactly what the scheduled
    cycle must end in)."""
    rec = _approved_record("fo_test_release_1", "Test Release Office LLC")
    state: dict = {
        "records": [rec.model_dump(mode="json")],
        "classified": [{"name": rec.name, "fo_id": rec.fo_id,
                         "fo_type": rec.fo_type.value,
                         "confidence": "High", "evident": True}],
        # governance decisions are exactly what release consumes
        "decisions": [{"name": rec.name, "fo_id": rec.fo_id, "action": "approve",
                       "reason": "approved by policy", "confidence": 0.90}],
    }

    from fointel.operate.orchestrator import Task
    orch = Orchestrator()
    orch.register_defaults()
    out = orch.agents["release"].execute(Task(
        task_id="t", agent="release", action="release.publish",
        payload={"state": state, "out_dir": str(tmp_path)}))
    assert out["count"] == 1
    assert state["approved"] == ["Test Release Office LLC"]

    store = json.loads((tmp_path / "records.json").read_text(encoding="utf-8"))
    assert [r["fo_id"] for r in store] == ["fo_test_release_1"]
    csv = (tmp_path / "family_offices.csv").read_text(encoding="utf-8", errors="replace")
    assert "Test Release Office LLC" in csv
    assert (tmp_path / "family_offices.xlsx").exists()


def test_release_never_drops_curated_store(employees, tmp_path: Path) -> None:
    """merging new approved records must NEVER delete the existing curated store —
    existing records win by fo_id, new ones are added."""

    def _curated(fo_id: str, name: str) -> FamilyOfficeRecord:
        return FamilyOfficeRecord(
            fo_id=fo_id, name=name, fo_type=FOType.UNDETERMINED,
            discovery_source=SourceClass.DIRECTORY, data_as_of=date(2025, 1, 1))

    curated = _curated("fo_curated_1", "Established Family Office")
    (tmp_path / "records.json").write_text(
        json.dumps([curated.model_dump(mode="json")]), encoding="utf-8")

    new = _approved_record("fo_test_release_2", "New Release Office LLC")
    state: dict = {
        "records": [new.model_dump(mode="json")],
        "decisions": [{"name": new.name, "fo_id": new.fo_id, "action": "approve",
                       "confidence": 0.90}],
    }
    from fointel.operate.orchestrator import Task
    orch = Orchestrator()
    orch.register_defaults()
    out = orch.agents["release"].execute(Task(
        task_id="t", agent="release", action="release.publish",
        payload={"state": state, "out_dir": str(tmp_path)}))
    assert out["count"] == 1
    assert out["store_total"] == 2

    store = json.loads((tmp_path / "records.json").read_text(encoding="utf-8"))
    ids = sorted(r["fo_id"] for r in store)
    assert ids == ["fo_curated_1", "fo_test_release_2"]


def test_release_is_noop_on_empty_window(employees, tmp_path: Path) -> None:
    """an empty window (no approved records) writes NOTHING and leaves the store
    untouched — the quiet-cycle invariant all other tests rely on."""
    state: dict = {"records": [], "decisions": []}
    from fointel.operate.orchestrator import Task
    orch = Orchestrator()
    orch.register_defaults()
    out = orch.agents["release"].execute(Task(
        task_id="t", agent="release", action="release.publish",
        payload={"state": state, "out_dir": str(tmp_path)}))
    assert out["count"] == 0
    assert not (tmp_path / "records.json").exists()
    assert state["approved"] == []