"""
Release gates — the single authority for dataset publication.

No record reaches the delivered dataset except through `ReleaseGate`. Every gate
is mandatory; a record ships only if ALL pass. Failures are recorded with reasons
and logged to the `release` channel. This is where "findings govern releases"
becomes true in code, not documentation (gate-review A1).

The gates encode config/inclusion_standard.md:
  G1 family_office_evidenced ............ Rule 2 (affirmative FO evidence)
  G2 classification_evidence ............ a typed SFO/MFO carries evidence
  G3 discovery_documented ............... how the firm was found is recorded
  G4 verification_documented ............ >=1 authoritative verification source
  G5 verification_authoritative ......... discovery-only sources never verify
  G6 no_contradictions .................. discovery != verification (independence)
  G7 mandatory_fields_complete .......... name + type + geography + actionable path
  G8 provenance_complete ................ Rule 1 (every populated cell has a basis)
  G9 no_rejected_values_shipped ......... a value in the audit trail never appears
                                          in any delivered field
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..observability import get_logger
from ..schema import AuditEntry, FamilyOfficeRecord, FOType, SourceClass

log = get_logger("release")

# Discovery-only source classes may never appear as verification (inclusion_standard).
DISCOVERY_ONLY: set[SourceClass] = {SourceClass.DIRECTORY}


class GateCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class GateOutcome(BaseModel):
    fo_id: str
    passed: bool
    checks: list[GateCheck]

    def failures(self) -> list[GateCheck]:
        return [c for c in self.checks if not c.passed]


class ReleaseGate:
    """Evaluates records against the mandatory gates and is the only path to release."""

    def __init__(self, audit_by_fo: Optional[dict[str, list[AuditEntry]]] = None):
        # audit trail per fo_id — used to prove no rejected value is shipped
        self.audit_by_fo = audit_by_fo or {}

    def evaluate(self, rec: FamilyOfficeRecord) -> GateOutcome:
        checks: list[GateCheck] = []

        # G1 — Rule 2
        checks.append(GateCheck(
            name="family_office_evidenced", passed=rec.qualifies(),
            detail="affirmative FO evidence present" if rec.qualifies()
            else "no affirmative FO evidence (fo_type_evidence missing)"))

        # G2 — a typed SFO/MFO must carry classification evidence
        typed = rec.fo_type in (FOType.SFO, FOType.MFO)
        checks.append(GateCheck(
            name="classification_evidence", passed=(not typed) or bool(rec.fo_type_evidence),
            detail="typed FO carries evidence" if (not typed or rec.fo_type_evidence)
            else f"typed {rec.fo_type.value} without classification evidence"))

        # G3 — discovery documented
        checks.append(GateCheck(
            name="discovery_documented", passed=rec.discovery_source is not None,
            detail=rec.discovery_source.value if rec.discovery_source else "missing"))

        # G4 — at least one authoritative (non-discovery-only) verification source
        authoritative = [s for s in rec.verification_sources if s.source_class not in DISCOVERY_ONLY]
        checks.append(GateCheck(
            name="verification_documented", passed=len(authoritative) >= 1,
            detail=f"{len(authoritative)} authoritative verification source(s)"))

        # G5 — discovery-only sources (Wikipedia/Wikidata) may never verify
        misused = [s.source_class.value for s in rec.verification_sources
                   if s.source_class in DISCOVERY_ONLY]
        checks.append(GateCheck(
            name="verification_authoritative", passed=not misused,
            detail="ok" if not misused else f"discovery-only source used to verify: {misused}"))

        # G6 — discovery != verification (independence), unless justified
        warnings = rec.independence_warnings()
        checks.append(GateCheck(
            name="no_contradictions", passed=not warnings,
            detail="; ".join(warnings) if warnings else "none"))

        # G7 — mandatory fields + at least one actionable / entity-intelligence path
        geography_ok = bool(rec.hq_country or rec.hq_state or rec.hq_city)
        actionable = bool(rec.principal_email or rec.principal_phone or rec.principal_linkedin
                          or rec.hq_phone or rec.website or rec.investment_thesis or rec.signals)
        missing = []
        if not rec.name:
            missing.append("name")
        if not geography_ok:
            missing.append("geography")
        if not actionable:
            missing.append("actionable_or_entity_intelligence")
        checks.append(GateCheck(
            name="mandatory_fields_complete", passed=not missing,
            detail="complete" if not missing else f"missing: {missing}"))

        # G8 — Rule 1 provenance completeness
        violations = rec.provenance_violations()
        checks.append(GateCheck(
            name="provenance_complete", passed=not violations,
            detail="complete" if not violations
            else "; ".join(f"{f}:{r}" for f, r in violations)))

        # G9 — no value that was rejected to audit appears in any delivered field
        leaked = self._leaked_values(rec)
        checks.append(GateCheck(
            name="no_rejected_values_shipped", passed=not leaked,
            detail="ok" if not leaked else f"rejected value in delivered field: {leaked}"))

        passed = all(c.passed for c in checks)
        return GateOutcome(fo_id=rec.fo_id, passed=passed, checks=checks)

    def _leaked_values(self, rec: FamilyOfficeRecord) -> list[str]:
        rejected = {a.rejected_value for a in self.audit_by_fo.get(rec.fo_id, []) if a.rejected_value}
        if not rejected:
            return []
        row = rec.to_delivery_row()
        return sorted({v for v in row.values() if isinstance(v, str) and v and v in rejected})

    def publish(self, records: list[FamilyOfficeRecord]
                ) -> tuple[list[FamilyOfficeRecord], list[GateOutcome]]:
        """The ONLY sanctioned path to a released dataset. Returns (released, outcomes)."""
        released: list[FamilyOfficeRecord] = []
        outcomes: list[GateOutcome] = []
        for rec in records:
            outcome = self.evaluate(rec)
            outcomes.append(outcome)
            if outcome.passed:
                released.append(rec)
                log.info("released", extra={"event": "release", "fo_id": rec.fo_id, "firm": rec.name})
            else:
                log.warning("withheld", extra={
                    "event": "withhold", "fo_id": rec.fo_id, "firm": rec.name,
                    "failed_gates": [c.name for c in outcome.failures()]})
        log.info("publish complete", extra={
            "event": "publish_done", "released": len(released),
            "withheld": len(records) - len(released), "total": len(records)})
        return released, outcomes
