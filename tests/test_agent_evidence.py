"""Unit tests for the deterministic evidence/scoring layer of the mandate agent.

No network, no LLM — this is exactly the part of the agent design that must NOT
depend on a model (see docs/AgentArchitecture.md section 2). understand_mandate
and explain_and_recommend are exercised separately, live, in the goal runs
under reports/goals/ and logs/agent/ — this file only covers the fixed,
auditable scoring formula.
"""

from __future__ import annotations

from src.fointel.agent.evidence import build_evidence, score_and_classify


def _rec(**overrides):
    base = {
        "fo_id": "fo_test1", "name": "Test Family Office", "fo_type": "Multi-Family Office",
        "fo_type_evidence": "site self-identifies as a family office",
        "record_confidence": "Medium",
        "verification_sources": [
            {"source_class": "Firm Website", "verifies": "type"},
            {"source_class": "SEC IAPD / Form ADV", "verifies": "registration"},
        ],
        "signals": [], "investing_sectors": ["healthcare"],
        "investment_thesis": "We invest in healthcare services businesses.",
        "hq_state": "TX", "hq_country": "US",
        "principal_name": None, "principal_title": None,
        "principal_email": None, "principal_email_status": None,
        "principal_linkedin": None, "principal_phone": None,
        "firm_contact_email": "info@testfo.com",
        "data_as_of": "2026-08-01",
    }
    base.update(overrides)
    return base


def test_sector_match_scores_higher_than_no_match():
    criteria = {"sectors": ["healthcare"], "geography": []}
    matched = build_evidence(_rec(), criteria)
    score_and_classify(matched, criteria)
    unmatched = build_evidence(_rec(investing_sectors=["real estate"], investment_thesis="We invest in real estate."), criteria)
    score_and_classify(unmatched, criteria)
    assert matched.sector_match is True
    assert unmatched.sector_match is False
    assert matched.fit_score > unmatched.fit_score


def test_no_stated_sector_is_not_a_strike():
    """A mandate with no sector criterion must not penalize every record for
    'failing' a match that was never requested (the real bug found and fixed
    in this session — see git history for agent/evidence.py)."""
    criteria = {"sectors": [], "geography": []}
    ev = build_evidence(_rec(), criteria)
    score_and_classify(ev, criteria)
    assert ev.uncertainty != "thin" or "unstated mandate fit" in ev.uncertainty_reason
    # with >=2 sources, a thesis on file, and nothing stated to fail, this
    # must be able to reach "sufficient" — not be trapped at "thin" forever.
    assert ev.uncertainty == "sufficient"


def test_generic_inbox_is_never_a_contact_route():
    criteria = {"sectors": [], "geography": []}
    ev = build_evidence(_rec(firm_contact_email="info@testfo.com", principal_email=None), criteria)
    score_and_classify(ev, criteria)
    assert ev.contact_route is None


def test_named_person_email_is_a_contact_route():
    criteria = {"sectors": [], "geography": []}
    ev = build_evidence(_rec(principal_name="Jane Smith", principal_title="CIO",
                             principal_email="jane@testfo.com", principal_email_status="risky"), criteria)
    score_and_classify(ev, criteria)
    assert ev.contact_route is not None
    assert ev.contact_route["kind"] == "principal_email"


def test_zero_evidence_record_is_insufficient():
    criteria = {"sectors": ["healthcare"], "geography": []}
    ev = build_evidence(_rec(fo_type="Undetermined", fo_type_evidence=None,
                             verification_sources=[], investing_sectors=[], investment_thesis=None), criteria)
    score_and_classify(ev, criteria)
    assert ev.uncertainty == "insufficient"


def test_stale_record_is_flagged_even_with_good_sector_match():
    criteria = {"sectors": ["healthcare"], "geography": []}
    ev = build_evidence(_rec(data_as_of="2020-01-01"), criteria)
    score_and_classify(ev, criteria)
    assert ev.uncertainty == "stale"


def test_confidence_never_exceeds_evidence_bounds():
    """fit_score is always in [0, 1] regardless of input combination."""
    criteria = {"sectors": ["healthcare"], "geography": ["TX"]}
    for conf in ("High", "Medium", "Low"):
        ev = build_evidence(_rec(record_confidence=conf), criteria)
        score_and_classify(ev, criteria)
        assert 0.0 <= ev.fit_score <= 1.0
