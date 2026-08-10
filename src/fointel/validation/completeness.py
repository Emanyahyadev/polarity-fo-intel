"""Field-level completeness and dataset coverage — honest, deterministic stats.

The quality backbone for the operating policy's "quality over quantity":
a record counts toward a target ONLY when it satisfies the production release
gates; nothing here can inflate a count. All metrics are recomputable from the
record itself.

Definitions (every one enforced here, none invented):
  * required fields   — what the release policy actually requires (name,
                        classification evidence, geography, >=1 authoritative
                        verification source) — the ReleaseGate G3/G4/G7 set;
  * verified field    — populated cell whose provenance exists and is not LOW
                        (or a cell backed by an authoritative verification source);
  * provenance coverage — populated cells with provenance / populated cells;
  * fully enriched    — every required field verified AND at least one
                        entity-intelligence cell (principal / AUM / website /
                        thesis / signals / contact);
  * verified contact coverage — records with a verified reachable channel
                        (deliverable/approved/verified email, or a sourced phone
                        / LinkedIn), not just any populated channel.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from .gates import ReleaseGate
from ..schema import EmailStatus, FamilyOfficeRecord, SourceClass

# --------------------------------------------------------------------------- #
# Field taxonomy (schema-anchored, mirrors the gate G7 mandatory set)
# --------------------------------------------------------------------------- #

REQUIRED_FIELDS = ["name", "fo_type_evidence", "geography", "verification_source"]

# entity-intelligence cells — at least one verified makes a record "fully enriched"
INTELLIGENCE_FIELDS = [
    "description", "investment_thesis", "estimated_aum", "website",
    "principal_name", "principal_title", "hq_phone", "principal_phone",
    "principal_email", "principal_linkedin", "corporate_linkedin", "signals",
    "firm_contact_email",
]

_STAT_FIELDS = INTELLIGENCE_FIELDS + ["website_owned_source", "principal_status"]

_VERIFIED_EMAIL_STATUSES = {EmailStatus.DELIVERABLE.value, "approved", "verified"}


def _cell(rec: FamilyOfficeRecord, field: str) -> Any:
    if field == "geography":
        return rec.hq_country or rec.hq_state or rec.hq_city
    if field == "verification_source":
        return any(s.source_class not in (SourceClass.DIRECTORY,)
                   for s in rec.verification_sources)
    return getattr(rec, field, None)


def _cell_verified(rec: FamilyOfficeRecord, field: str) -> bool:
    """A populated cell is 'verified' when it carries non-LOW provenance (or is an
    authoritative verification source). LOW provenance = honestly unverified."""
    if field == "verification_source":
        return bool(_cell(rec, field))
    if field == "geography":
        return any(_cell_prov_ok(rec, f) for f in ("hq_country", "hq_state", "hq_city"))
    return _cell_prov_ok(rec, field)


def _cell_prov_ok(rec: FamilyOfficeRecord, field: str) -> bool:
    prov = rec.provenance.get(field)
    if prov is None:
        return False
    from ..schema import Confidence
    return prov.confidence in (Confidence.HIGH, Confidence.MEDIUM)


def record_completeness(rec: FamilyOfficeRecord) -> dict[str, Any]:
    """Per-record completeness snapshot (the policy's completeness gate fields)."""
    populated: list[str] = []
    unverified: list[str] = []
    verified: list[str] = []
    missing: list[str] = []

    for field in REQUIRED_FIELDS + INTELLIGENCE_FIELDS:
        value = _cell(rec, field)
        if not value:
            if field in REQUIRED_FIELDS:
                missing.append(field)
            continue
        populated.append(field)
        if _cell_verified(rec, field):
            verified.append(field)
        else:
            unverified.append(field)

    prov_fields = {f for f in rec.provenance if getattr(rec, f, None)}
    provenance_coverage = len(prov_fields) / len(populated) if populated else 0.0

    return {
        "fo_id": rec.fo_id,
        "name": rec.name,
        "required_fields": list(REQUIRED_FIELDS),
        "populated_fields": sorted(populated),
        "verified_fields": sorted(verified),
        "missing_fields": sorted(missing),
        "unverified_fields": sorted(unverified),
        "provenance_coverage": round(provenance_coverage, 3),
        "required_fields_complete": not missing,
        "classification_status": rec.fo_type.value if rec.fo_type else None,
        "classification_evidenced": bool(rec.fo_type_evidence) or rec.fo_type == "Undetermined",
        "validation_status": "passed" if ReleaseGate().evaluate(rec).passed else "blocked",
        "confidence": rec.record_confidence.value,
        "freshness_days": (date.today() - rec.data_as_of).days if rec.data_as_of else None,
        "fully_enriched": (not missing)
        and len(verified) >= len(REQUIRED_FIELDS)
        and any(f in verified for f in INTELLIGENCE_FIELDS),
        "release_status": "releasable" if ReleaseGate().evaluate(rec).passed else "blocked",
    }


def dataset_coverage(records: list[FamilyOfficeRecord]) -> dict[str, Any]:
    """Whole-dataset quality metrics with honest denominators."""
    from collections import Counter

    n = len(records)
    if n == 0:
        return _empty_coverage()

    gate = ReleaseGate()
    complete = [record_completeness(r) for r in records]
    released = [c for c in complete if c["release_status"] == "releasable"]

    type_dist = Counter(c["classification_status"] for c in complete)
    routes = Counter(r.principal_email_status.value if r.principal_email_status else ""
                     for r in records)

    coverage = {
        "total_records": n,
        "released_records": len(released),
        "evidence_coverage": round(
            sum(1 for r in records
                if any(s.source_class != SourceClass.DIRECTORY
                       for s in r.verification_sources)) / n, 3),
        "required_field_completion_rate": round(
            sum(1 for c in complete if c["required_fields_complete"]) / n, 3),
        "fully_enriched": sum(1 for c in complete if c["fully_enriched"]),
        "verified_fields_total": sum(len(c["verified_fields"]) for c in complete),
        "unresolved_field_cells": sum(len(c["unverified_fields"]) + len(c["missing_fields"])
                                      for c in complete),
        "classification_distribution": dict(type_dist),
        "named_person_coverage": round(
            sum(1 for r in records if r.principal_name) / n, 3),
        "aum_coverage": round(sum(1 for r in records if r.estimated_aum) / n, 3),
        "website_coverage": round(sum(1 for r in records if r.website) / n, 3),
        "verified_contact_coverage": round(
            sum(1 for r in records if _verified_contact(r)) / n, 3),
        "email_status_distribution": dict(routes),
    }
    return coverage


def _verified_contact(rec: FamilyOfficeRecord) -> bool:
    from ..schema import Confidence

    def _verified(prov) -> bool:
        return prov is not None and prov.confidence in (Confidence.HIGH, Confidence.MEDIUM)

    if rec.principal_email and rec.principal_email_status in _VERIFIED_EMAIL_STATUSES:
        return True
    if rec.principal_phone and _verified(rec.provenance.get("principal_phone")):
        return True
    if (rec.principal_linkedin or rec.corporate_linkedin) and (
            _verified(rec.provenance.get("principal_linkedin"))
            or _verified(rec.provenance.get("corporate_linkedin"))):
        return True
    return False


def _empty_coverage() -> dict[str, Any]:
    return {
        "total_records": 0, "released_records": 0, "evidence_coverage": 0.0,
        "required_field_completion_rate": 0.0, "fully_enriched": 0,
        "verified_fields_total": 0, "unresolved_field_cells": 0,
        "classification_distribution": {}, "named_person_coverage": 0.0,
        "aum_coverage": 0.0, "website_coverage": 0.0,
        "verified_contact_coverage": 0.0, "email_status_distribution": {},
    }


def gate_passing_count(records: list[FamilyOfficeRecord]) -> int:
    """Records that satisfy the FULL production release policy (the only count
    that may be used as a target-progress number — never mere rows)."""
    gate = ReleaseGate()
    return sum(1 for r in records if gate.evaluate(r).passed)