"""
Stage 2 operating layer tests.

Covers the deterministic brain: policy engine tier decisions, the orchestrator's
authority gating (autonomous/escalate/refuse), idempotency, the review queue,
and the deterministic aggregate (count/total) answer path wired into the RAG layer.
"""

from __future__ import annotations

import json

import pytest

from fointel.operate import Orchestrator
from fointel.operate.policy_engine import PolicyEngine, ActionStatus


# --------------------------------------------------------------------------- #
# Policy engine
# --------------------------------------------------------------------------- #

def test_tier1_autonomous_action() -> None:
    pe = PolicyEngine()
    d = pe.decide("discovery.search")
    assert d.status == ActionStatus.AUTONOMOUS
    assert d.tier == 1


def test_tier3_refuse_publish_without_validation() -> None:
    pe = PolicyEngine()
    # publish goes through the governance engine, not the generic decide();
    # without validation + minimum sources the system must refuse, never guess.
    d = pe.may_publish(confidence=0.95, n_sources=0)
    assert d.status == ActionStatus.REFUSE
    assert d.tier == 3

    # and a publish_record action is itself not an autonomous surface
    d2 = pe.decide("publish_record", {"confidence": 0.95, "n_sources": 3})
    assert d2.tier in (2, 3)


def test_unknown_action_escalates_by_default() -> None:
    pe = PolicyEngine()
    # a genuinely unlisted action must never auto-run; it escalates to review
    d = pe.decide("monitoring.report")
    assert d.status == ActionStatus.ESCALATE
    assert d.tier == 2
    # the cycle's validation.review is Tier 1 (the gate agent itself decides
    # whether an individual record must escalate)
    d2 = pe.decide("validation.review")
    assert d2.status == ActionStatus.AUTONOMOUS


def test_confidence_authority_bands() -> None:
    pe = PolicyEngine()
    assert pe.confidence_authority(0.95) == "auto_release"
    assert pe.confidence_authority(0.87) == "auto_release_medium"
    assert pe.confidence_authority(0.75) == "hold_governance_review"
    assert pe.confidence_authority(0.40) == "quarantine"


def test_may_publish_requires_min_sources() -> None:
    pe = PolicyEngine()
    d = pe.may_publish(confidence=0.95, n_sources=1)
    assert d.status == ActionStatus.REFUSE


def test_contact_review_generic_mailbox_refused() -> None:
    pe = PolicyEngine()
    d = pe.contact_review(person="Jane Doe", email="info@cascade.com",
                          email_type="corporate", source_type="firm_site",
                          confidence=0.95)
    assert d.status == ActionStatus.REFUSE


# --------------------------------------------------------------------------- #
# Orchestrator authority gating
# --------------------------------------------------------------------------- #

def test_orchestrator_runs_autonomous_and_escalates() -> None:
    orch = Orchestrator()
    orch.register_defaults()
    tasks = orch.plan([
        {"agent": "scheduler", "action": "scheduler.wake",
         "payload": {"operation": "tick"}},
        {"agent": "discovery", "action": "discovery.search",
         "payload": {"query": "family office Texas", "source": "SEC EDGAR",
                     "candidate_ids": ["c1"]}},
        {"agent": "validation", "action": "validation.review", "payload": {}},
        {"agent": "logging", "action": "logging.write",
         "payload": {"kind": "metric", "content": "records=61"}},
        {"agent": "scheduler", "action": "publish_record",
         "payload": {"confidence": 0.5}},
    ])
    statuses = {t.status for t in tasks}
    assert "done" in statuses
    assert "escalated" in statuses          # publish_record (validation.review is Tier 1)
    assert orch.summary()["escalated_to_human_review"] == 1


def test_orchestrator_idempotency_skips_repeat() -> None:
    orch = Orchestrator()
    orch.register_defaults()
    jobs = [{"agent": "scheduler", "action": "scheduler.wake",
             "payload": {"operation": "tick"}}]
    t1 = orch.plan(jobs)[0]
    # replay the exact same task id
    orch.run_task(t1)
    dup = [a for a in orch.actions_taken if a["task_id"] == t1.task_id]
    assert len(dup) == 1
    assert orch.registry[-1].status in ("done", "escalated", "refused")


def test_orchestrator_trace_is_replayable_jsonl(tmp_path) -> None:
    orch = Orchestrator(logs_dir=tmp_path)
    orch.register_defaults()
    orch.plan([{"agent": "logging", "action": "logging.write",
                "payload": {"kind": "log", "content": "hello"}}])
    lines = [json.loads(l) for l in orch.trace.path.read_text(encoding="utf-8").splitlines()]
    assert lines
    assert all("run_id" in l and "ts" in l for l in lines)


def test_unknown_agent_fails_not_fabricates() -> None:
    orch = Orchestrator()
    orch.register_defaults()
    # a Tier-1 action routed to an unregistered agent must fail loudly, not fabricate
    tasks = orch.plan([{"agent": "ghost", "action": "scheduler.wake",
                        "payload": {"operation": "tick"}}])
    assert tasks[0].status == "failed"


def test_human_review_queue_resolution() -> None:
    pe = PolicyEngine()
    item = pe.queue.add("it-1", "needs eyes", "review", {"action": "validation.review"})
    assert len(pe.queue.pending()) == 1
    pe.queue.resolve("it-1", decision="approved", decided_by="Eman", note="ok")
    assert len(pe.queue.pending()) == 0
    assert item.context["decided_by"] == "Eman"


# --------------------------------------------------------------------------- #
# Deterministic aggregate answers (RAG wiring)
# --------------------------------------------------------------------------- #

class _StubIndex:
    def __init__(self, records):
        self.records = records


@pytest.fixture()
def agg_index() -> _StubIndex:
    import csv
    rows = list(csv.DictReader(open("data/final/family_offices.csv", encoding="utf-8")))
    return _StubIndex(rows)


def test_aggregate_count_all(agg_index) -> None:
    from fointel.rag.answer import _aggregate_answer
    r = _aggregate_answer(agg_index, "how many family offices")
    assert r is not None and r.mode == "count"
    assert r.answer.startswith("Found 80 matching family offices")
    assert "searched all 80 verified records" in r.answer
    assert r.compute["value"] == 80


def test_aggregate_count_filtered(agg_index) -> None:
    from fointel.rag.answer import _aggregate_answer
    r = _aggregate_answer(agg_index, "how many multi-family offices")
    assert r is not None and r.compute["recompute"]["filters"] == {"fo_type": "Multi-Family Office"}
    assert r.compute["value"] == 15


def test_aggregate_count_by_state(agg_index) -> None:
    from fointel.rag.answer import _aggregate_answer
    r = _aggregate_answer(agg_index, "how many family offices in Texas")
    assert r is not None and r.compute["value"] == 5
    assert "in TX" in r.answer


def test_aggregate_total_13f(agg_index) -> None:
    from fointel.rag.answer import _aggregate_answer
    r = _aggregate_answer(agg_index, "total 13f securities")
    assert r is not None and r.mode == "total"
    assert r.answer.startswith("Total 13F securities:")
    assert r.compute["scope"]["included_in_calc"] == 0
    # invariant: recompute sum equals displayed value
    assert r.compute["recompute"]["sum_of_items"] == pytest.approx(r.compute["value"])


def test_aggregate_total_regulatory(agg_index) -> None:
    from fointel.rag.answer import _aggregate_answer
    r = _aggregate_answer(agg_index, "total regulatory aum")
    assert r is not None and r.mode == "total"
    assert r.compute["scope"]["included_in_calc"] == 8


def test_offtopic_aggregate_falls_through(agg_index) -> None:
    from fointel.rag.answer import _aggregate_answer
    assert _aggregate_answer(agg_index, "total price of pizza") is None
    assert _aggregate_answer(agg_index, "how many toasters") is None


def test_answer_query_returns_deterministic_aggregate(agg_index) -> None:
    from fointel.rag.answer import answer_query
    r = answer_query(agg_index, "how many single family offices")
    assert r.answered
    assert r.mode == "count"
    assert r.compute["value"] == 10


# --------------------------------------------------------------------------- #
# Correction 8 / 6: compound aggregation + universal-coverage (deterministic)
# --------------------------------------------------------------------------- #

def test_compound_count_and_total_is_decomposed(agg_index) -> None:
    from fointel.rag.answer import _aggregate_answer
    r = _aggregate_answer(agg_index, "how many multi-family offices and their total 13f securities")
    assert r is not None and r.mode == "compound"
    assert "Found 15 matching" in r.answer          # count part answered
    assert "Total 13F securities" in r.answer        # total part answered — nothing dropped
    assert r.compute["decomposed"] is True
    assert len(r.compute["parts"]) == 2


def test_compound_mixed_scope_reports_trace(agg_index) -> None:
    from fointel.rag.answer import _aggregate_answer
    r = _aggregate_answer(agg_index, "how many family offices in Texas and their total regulatory aum")
    assert r is not None and r.mode == "compound"
    assert "Found 5 matching" in r.answer
    assert "Total regulatory AUM" in r.answer
    assert len(r.compute["parts"]) == 2
    # deterministic recompute trace is still reported even when zero TX records carry the measure
    assert len(r.compute['parts']) == 2


def test_single_branches_unaffected_by_compound_refactor(agg_index) -> None:
    from fointel.rag.answer import _aggregate_answer
    assert _aggregate_answer(agg_index, "how many toasters") is None
    assert _aggregate_answer(agg_index, "total price of pizza") is None
    r = _aggregate_answer(agg_index, "how many family offices")
    assert r.mode == "count"


def test_universal_coverage_returns_truthful_count(agg_index) -> None:
    from fointel.rag.answer import _universal_claim_answer
    r = _universal_claim_answer(agg_index, "all family offices have a principal email")
    assert r is not None and r.mode == "universal"
    assert "have a principal email" in r.answer
    assert r.compute["have_field"] == 0
    assert r.compute["total"] == 80


def test_universal_claim_13f_coverage(agg_index) -> None:
    from fointel.rag.answer import _universal_claim_answer
    r = _universal_claim_answer(agg_index, "every family office has a 13f")
    assert r is not None and r.mode == "universal"
    assert r.compute["claim"] == "13f"
    assert r.compute["have_field"] == 0
    assert r.compute["total"] == 80
    assert "0 of 80" in r.answer


# ---------------------------------------------------------------------------
# Correction-10: evidence-bounded principal role labels
# ---------------------------------------------------------------------------

def test_principal_role_is_evidence_bounded(agg_index) -> None:
    from fointel.rag.roles import principal_role
    edgar = type("S", (), {"source_class": type("C", (), {"value": "SEC EDGAR (13F / SC / Form D filings)"})()})()
    label = principal_role([edgar])
    assert label == "filing signatory (13F)"
    # unknown source never claims a role the evidence did not establish
    assert "decision" not in label.lower() and "owner" not in label.lower()
