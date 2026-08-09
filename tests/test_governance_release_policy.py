"""Governance -> Release policy enforcement (Phase 5).

M8 — the release boundary RE-ASSERTS the release gates: governance approval is
necessary but never sufficient; only gate-passing records enter the canonical
store. Covers the propagated-audit G9 (a rejected value must never ship) and the
honest "withheld" accounting in the release report.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from fointel.operate import Orchestrator
from fointel.operate.adapters import load_employees
from fointel.operate.orchestrator import Task
from fointel.schema import (AuditEntry, Confidence, FamilyOfficeRecord, FOType,
                            Provenance, SourceClass)


def _prov(sc=SourceClass.SEC_IAPD, conf=Confidence.HIGH) -> Provenance:
    return Provenance(source_class=sc, method="SEC IAPD registration",
                      checked_at=date(2026, 8, 1), confidence=conf)


def _rec(fo_id: str, name: str, *, provenance: dict | None = None) -> FamilyOfficeRecord:
    return FamilyOfficeRecord(
        fo_id=fo_id, name=name, fo_type=FOType.SFO,
        fo_type_evidence="SEC IAPD registration; firm website",
        fo_type_confidence=Confidence.HIGH, hq_country="United States",
        website="https://clean.example.com",
        estimated_aum="$100M (SEC Form ADV Item 5.F)",
        discovery_source=SourceClass.SEC_EDGAR, data_as_of=date(2026, 8, 1),
        record_confidence=Confidence.HIGH,
        verification_sources=[
            {"source_class": SourceClass.SEC_IAPD.value,
             "verifies": "firm registration", "accessed_at": "2026-08-01"},
            {"source_class": SourceClass.FIRM_SITE.value,
             "verifies": "self-identification", "accessed_at": "2026-08-01"},
        ],
        provenance=provenance if provenance is not None else {
            f: _prov() for f in ("name", "fo_type", "fo_type_evidence",
                                 "hq_country", "website", "estimated_aum")},
    )


@pytest.fixture()
def orch() -> Orchestrator:
    o = Orchestrator()
    o.register_defaults()
    return o


def _release(orch: Orchestrator, records: list, decisions: list,
             tmp_path: Path) -> dict:
    payload = {"state": {"records": [r.model_dump(mode="json") for r in records]},
               "decisions": decisions, "out_dir": str(tmp_path)}
    return orch.agents["release"].execute(Task(
        task_id="t", agent="release", action="release.publish", payload=payload))


def _approve(fo_id: str, name: str) -> dict:
    return {"name": name, "fo_id": fo_id, "action": "approve", "confidence": 0.90}


def test_release_withholds_gate_blocked_approved_record(orch, tmp_path: Path):
    """Approved by governance but missing provenance on a populated cell (G8)
    must NOT ship — the release boundary re-asserts the gates."""
    blocked = _rec("fo_blocked", "Blocked Office LLC",
                   provenance={k: _prov() for k in ("name",)})
    out = _release(orch, [blocked], [_approve("fo_blocked", "Blocked Office LLC")],
                   tmp_path)
    assert out["count"] == 0
    assert out["withheld"] == [{"fo_id": "fo_blocked",
                                "failed": ["provenance_complete"]}]
    assert not (tmp_path / "records.json").exists()          # store untouched


def test_release_ships_gate_passing_approved_record(orch, tmp_path: Path):
    out = _release(orch, [_rec("fo_ok", "Clean Office LLC")],
                   [_approve("fo_ok", "Clean Office LLC")], tmp_path)
    assert out["count"] == 1 and out["withheld"] == []
    store = json.loads((tmp_path / "records.json").read_text("utf-8"))
    assert [r["fo_id"] for r in store] == ["fo_ok"]


def test_release_never_ships_rejected_value_from_audit(orch, tmp_path: Path):
    """G9 re-asserted at release: a value that appears in the audit trail as
    REJECTED may never ship in a new record."""
    leaked = _rec("fo_leak", "Leaky Office LLC", provenance={
        f: _prov() for f in ("name", "fo_type", "fo_type_evidence",
                             "hq_country", "website", "estimated_aum")})
    leaked.website = "https://rejected-domain.example"      # populated w/o prov too
    leaked.provenance["website"] = _prov()
    (tmp_path / "audit.json").write_text(json.dumps([
        AuditEntry(fo_id="fo_leak", field="website", rejected_value="https://rejected-domain.example",
                   reason="rejected in review", source_class=SourceClass.WEB,
                   checked_at=date(2026, 8, 1))
        .model_dump(mode="json")]), encoding="utf-8")
    out = _release(orch, [leaked], [_approve("fo_leak", "Leaky Office LLC")], tmp_path)
    assert out["count"] == 0
    assert out["withheld"][0]["failed"] == ["no_rejected_values_shipped"]
    assert not (tmp_path / "records.json").exists()


def test_release_partial_window_ships_only_passing(orch, tmp_path: Path):
    good = _rec("fo_good", "Good Office LLC")
    blocking = _rec("fo_bad", "Bad Office LLC", provenance={"name": _prov()})
    out = _release(orch, [good, blocking],
                   [_approve("fo_good", "Good Office LLC"),
                    _approve("fo_bad", "Bad Office LLC")], tmp_path)
    assert out["count"] == 1
    assert {w["fo_id"] for w in out["withheld"]} == {"fo_bad"}
    store = json.loads((tmp_path / "records.json").read_text("utf-8"))
    assert [r["fo_id"] for r in store] == ["fo_good"]

    empl = load_employees(orch.agents)
    assert empl["release"].contract.decision_rule.startswith(
        "release only records whose governance decision is approve")


def test_governance_escalation_carries_source_count():
    orch = Orchestrator()
    orch.register_defaults()
    owned = _rec("fo_owned", "Owned Source Office", provenance={
        f: _prov() for f in ("name", "fo_type", "fo_type_evidence",
                             "hq_country", "website", "estimated_aum")})
    res = orch.agents["governance"].execute(Task(
        task_id="g", agent="governance", action="governance.release_decision",
        payload={"state": {},
                 "classified": [{"name": "Owned Source Office", "fo_id": "fo_owned",
                                 "fo_type": "Single-Family Office",
                                 "confidence": "High", "evident": True}],
                 "records": [owned.model_dump(mode="json")]}))
    assert res["decisions"][0]["action"] == "approve"     # 2 authoritative sources
    assert res["decisions"][0]["n_sources"] == 2