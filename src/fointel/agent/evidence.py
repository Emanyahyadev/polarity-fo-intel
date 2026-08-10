"""
Deterministic retrieval planning, evidence gathering, scoring, and uncertainty
classification for the mandate agent.

Deliberately NOT model-driven: fit scoring and confidence are derived from
measured evidence (verification source count, sector/geography match,
freshness, contactability) via a fixed, auditable formula, never from an LLM
guessing a number. This mirrors the existing dataset rule that confidence is
derived from provenance, never set independently (config/inclusion_standard.md),
and it is the piece of "uncertainty handling" the brief requires be enforced in
control flow rather than only claimed in a prompt.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Optional

from ..compute import ComputeEngine
from ..rag.index import RetrievalIndex
from ..rag.retrieve import retrieve

STALE_DAYS = 400  # beyond this, data_as_of counts against freshness


@dataclass
class CandidateEvidence:
    fo_id: str
    name: str
    fo_type: str
    fo_type_evidence: Optional[str]
    record_confidence: str
    verification_sources: list[str]
    n_verification_sources: int
    signals: list[str]
    investing_sectors: list[str]
    investment_thesis: Optional[str]
    hq_state: Optional[str]
    hq_country: Optional[str]
    principal_name: Optional[str]
    principal_title: Optional[str]
    principal_email: Optional[str]
    principal_email_status: Optional[str]
    principal_linkedin: Optional[str]
    principal_phone: Optional[str]
    firm_contact_email: Optional[str]
    data_as_of: Optional[str]
    days_since_data_as_of: Optional[int]
    sector_match: bool
    geography_match: bool
    fit_score: float = 0.0
    uncertainty: str = "unclassified"     # sufficient | thin | conflicting | stale | insufficient
    uncertainty_reason: str = ""
    contact_route: Optional[dict] = None  # {"kind": ..., "value": ..., "evidence": ...} or None


def _contact_route(rec: dict) -> Optional[dict]:
    """A route counts only if it reaches the NAMED individual — never the firm's
    generic inbox, never a guessed/pattern email (config/inclusion_standard.md,
    Differentiator floor). firm_contact_email is deliberately never used here."""
    if rec.get("principal_email") and rec.get("principal_email_status") != "could_not_verify":
        return {"kind": "principal_email", "value": rec["principal_email"],
                "evidence": "named-person email, site/filing name-matched"}
    if rec.get("principal_linkedin"):
        return {"kind": "principal_linkedin", "value": rec["principal_linkedin"],
                "evidence": "principal's own current LinkedIn profile"}
    if rec.get("principal_phone"):
        return {"kind": "principal_phone", "value": rec["principal_phone"],
                "evidence": "authoritative filing (e.g. SEC 13F signature block)"}
    return None


def _days_since(iso_date: Optional[str]) -> Optional[int]:
    if not iso_date:
        return None
    try:
        d = dt.date.fromisoformat(iso_date)
        return (dt.date.today() - d).days
    except ValueError:
        return None


def build_evidence(rec: dict, criteria: dict) -> CandidateEvidence:
    sectors_wanted = [s.lower() for s in (criteria.get("sectors") or [])]
    geo_wanted = [g.lower() for g in (criteria.get("geography") or [])]
    rec_sectors = [s.lower() for s in (rec.get("investing_sectors") or [])]
    thesis = (rec.get("investment_thesis") or "").lower()
    desc = (rec.get("description") or "").lower()
    sector_match = bool(sectors_wanted) and any(
        s in rec_sectors or s in thesis or s in desc for s in sectors_wanted)
    geo_match = bool(geo_wanted) and (
        (rec.get("hq_state") or "").lower() in geo_wanted
        or (rec.get("hq_country") or "").lower() in geo_wanted)

    vsrc = rec.get("verification_sources") or []
    if isinstance(vsrc, str):
        vsrc_list = [s.strip() for s in vsrc.split(";") if s.strip()]
    else:
        vsrc_list = [
            (f"{v.get('source_class')} ({v.get('verifies')})" if isinstance(v, dict) else str(v))
            for v in vsrc
        ]

    signals = rec.get("signals") or []
    if isinstance(signals, str):
        signals = [s.strip() for s in signals.split(";") if s.strip()]
    else:
        signals = [(s.get("text") if isinstance(s, dict) else str(s)) for s in signals]

    das = rec.get("data_as_of")
    ev = CandidateEvidence(
        fo_id=rec.get("fo_id", ""), name=rec.get("name") or rec.get("family_office_name", ""),
        fo_type=rec.get("fo_type", "Undetermined"),
        fo_type_evidence=rec.get("fo_type_evidence") or None,
        record_confidence=rec.get("record_confidence", "Low"),
        verification_sources=vsrc_list, n_verification_sources=len(vsrc_list),
        signals=signals,
        investing_sectors=rec.get("investing_sectors") or [],
        investment_thesis=rec.get("investment_thesis") or None,
        hq_state=rec.get("hq_state") or None, hq_country=rec.get("hq_country") or None,
        principal_name=rec.get("principal_name") or None,
        principal_title=rec.get("principal_title") or None,
        principal_email=rec.get("principal_email") or None,
        principal_email_status=rec.get("principal_email_status") or None,
        principal_linkedin=rec.get("principal_linkedin") or None,
        principal_phone=rec.get("principal_phone") or None,
        firm_contact_email=rec.get("firm_contact_email") or None,
        data_as_of=das, days_since_data_as_of=_days_since(das),
        sector_match=sector_match, geography_match=geo_match,
    )
    ev.contact_route = _contact_route(rec)
    return ev


def score_and_classify(ev: CandidateEvidence, criteria: dict) -> None:
    """Mutates ev.fit_score / ev.uncertainty / ev.uncertainty_reason in place.
    Fixed, auditable weights — not model-guessed. Every point traces to a
    specific evidence fact so the score is independently recomputable."""
    score = 0.0
    reasons = []
    sector_specified = bool(criteria.get("sectors"))
    # A mandate that names no sector has nothing for a record to fail to match —
    # treat that as not-applicable, never as a strike against the record. Only a
    # STATED sector the record fails to match should ever lower confidence.
    sector_ok = ev.sector_match or not sector_specified

    if ev.sector_match:
        score += 0.35
    elif sector_specified:
        reasons.append("no stated sector/thesis match for the requested sector(s)")

    if ev.geography_match:
        score += 0.10
    elif criteria.get("geography"):
        reasons.append("headquarters not in the requested geography")

    if ev.fo_type_evidence:
        score += 0.15
    else:
        reasons.append("no affirmative family-office classification evidence on file")

    conf_bonus = {"High": 0.20, "Medium": 0.10, "Low": 0.0}.get(ev.record_confidence, 0.0)
    score += conf_bonus

    if ev.n_verification_sources >= 2:
        score += 0.10
    elif ev.n_verification_sources == 1:
        score += 0.03
    else:
        reasons.append("zero independent verification sources on file")

    if ev.signals:
        score += 0.05

    if ev.contact_route:
        score += 0.05
    else:
        reasons.append("no named-person contact route (generic firm inbox does not count)")

    stale = ev.days_since_data_as_of is not None and ev.days_since_data_as_of > STALE_DAYS
    if stale:
        score -= 0.10
        reasons.append(f"record data is {ev.days_since_data_as_of} days old (>{STALE_DAYS}-day staleness bar)")

    ev.fit_score = round(max(0.0, min(1.0, score)), 3)

    # Uncertainty classification — separate from fit score, drives the honesty
    # of the language shown to the customer. Weak evidence must read as weak,
    # never as a confident number with a caveat buried underneath.
    if ev.fo_type == "Undetermined" and not ev.fo_type_evidence:
        ev.uncertainty, ev.uncertainty_reason = "insufficient", "no affirmative FO evidence at all"
    elif stale:
        ev.uncertainty, ev.uncertainty_reason = "stale", "; ".join(reasons) or "data past staleness bar"
    elif ev.n_verification_sources == 0 and not sector_ok:
        ev.uncertainty, ev.uncertainty_reason = "insufficient", "; ".join(reasons)
    elif ev.n_verification_sources <= 1 or not sector_ok or not ev.investment_thesis:
        ev.uncertainty, ev.uncertainty_reason = "thin", "; ".join(reasons) or "single-source, or the mandate stated no sector to confirm fit against"
    else:
        ev.uncertainty, ev.uncertainty_reason = ("sufficient",
            "sector-matched with >=2 independent sources" if sector_specified
            else "no sector was specified to match against; >=2 independent sources and a stated investment thesis on file")


def plan_and_retrieve(criteria: dict, index: RetrievalIndex, engine: ComputeEngine,
                      trace) -> list[CandidateEvidence]:
    """Multi-step, multi-tool retrieval: a semantic pass per stated sector, a
    deterministic geography filter pass, and always a whole-dataset scan so a
    thin mandate is never silently narrowed away (Goal 2's requirement)."""
    steps = ["understand_mandate (LLM)", "plan_research (deterministic)"]
    sectors = list(criteria.get("sectors") or [])
    geos = criteria.get("geography") or []
    # A mandate with no stated sector still needs more than one retrieval pass
    # (Goal 1's "single retrieval call cannot answer" bar) — fall back to the
    # other structured criteria plus a fixed "recent activity" pass so the plan
    # never collapses to a single deterministic scan for a general mandate.
    if not sectors:
        for extra in (criteria.get("fund_stage_or_type"), criteria.get("role_sought"),
                     "recent investment activity"):
            if extra:
                sectors.append(extra)
    for s in sectors:
        steps.append(f"semantic retrieval: {s!r}")
    if geos:
        steps.append(f"deterministic filter: geography in {geos}")
    steps += ["evidence gathering per candidate", "deterministic fit scoring + uncertainty classification",
              "rank", "LLM synthesis grounded in the ranked evidence bundle"]
    trace.plan(steps)

    seen: dict[str, dict] = {}
    for s in sectors:
        hits = retrieve(index, s, top_k=25, filters={})
        fo_ids = [h.record.fo_id for h in hits]
        trace.retrieval(query=s, filters={}, hit_count=len(hits), fo_ids=fo_ids)
        for h in hits:
            seen[h.record.fo_id] = h.record.model_dump(mode="json") if hasattr(h.record, "model_dump") else dict(h.record)

    # Always also take a full-dataset deterministic pass so we do not silently
    # drop candidates a pure semantic query missed (Goal 2 explicitly forbids
    # cleaning uncertain records away before the run).
    all_recs = engine.records
    trace.tool_call("compute.full_scan", {"n": len(all_recs)}, {"scanned": len(all_recs)})
    for r in all_recs:
        seen.setdefault(r.get("fo_id"), r)

    if geos:
        before = len(seen)
        seen = {k: v for k, v in seen.items()
                if (v.get("hq_state") or "").lower() in [g.lower() for g in geos]
                or (v.get("hq_country") or "").lower() in [g.lower() for g in geos]
                or not sectors}  # if no sector given, geography alone should not eliminate everything silently
        trace.decision("geography_filter_applied", {"before": before, "after": len(seen)})

    evidences = []
    for fo_id, rec in seen.items():
        ev = build_evidence(rec, criteria)
        score_and_classify(ev, criteria)
        trace.evidence_ref(fo_id, "verification_sources", ",".join(ev.verification_sources) or "none",
                           note=f"n={ev.n_verification_sources}")
        trace.uncertainty_check(fo_id, ev.uncertainty, ev.uncertainty_reason)
        evidences.append(ev)

    evidences.sort(key=lambda e: e.fit_score, reverse=True)
    trace.comparison([{"fo_id": e.fo_id, "name": e.name, "fit_score": e.fit_score,
                       "uncertainty": e.uncertainty} for e in evidences[:30]])
    return evidences
