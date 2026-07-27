"""Release-gate tests, incl. the core invariant: a rejected value never reaches a delivered field."""

from datetime import date

from fointel.schema import (
    AuditEntry,
    Confidence,
    FamilyOfficeRecord,
    FOType,
    Provenance,
    SourceClass,
    SourceRef,
)
from fointel.validation.gates import ReleaseGate


def _prov(sc=SourceClass.FIRM_SITE) -> Provenance:
    return Provenance(source_class=sc, method="site fetch", checked_at=date(2026, 7, 27),
                      confidence=Confidence.HIGH)


def _releasable(**kw) -> FamilyOfficeRecord:
    """A record that passes every gate; individual tests break exactly one thing."""
    defaults = dict(
        fo_id="fo_1", name="Duquesne Family Office",
        fo_type=FOType.SFO, fo_type_evidence="reputable profile + SEC filer describe single-family office",
        fo_type_confidence=Confidence.HIGH,
        website="https://duquesne.example", hq_country="United States",
        discovery_source=SourceClass.SEC_EDGAR,
        verification_sources=[SourceRef(source_class=SourceClass.FIRM_SITE, verifies="firm type",
                                        accessed_at=date(2026, 7, 27))],
        data_as_of=date(2026, 7, 27),
        provenance={"name": _prov(SourceClass.SEC_EDGAR), "website": _prov(),
                    "hq_country": _prov(SourceClass.SEC_EDGAR)},
    )
    defaults.update(kw)
    return FamilyOfficeRecord(**defaults)


def _gate(audit=None):
    return ReleaseGate(audit_by_fo=audit or {})


def test_fully_valid_record_is_released():
    released, outcomes = _gate().publish([_releasable()])
    assert len(released) == 1 and outcomes[0].passed


def test_missing_fo_evidence_blocks_release():
    rec = _releasable(fo_type=FOType.UNDETERMINED, fo_type_evidence=None)
    out = _gate().evaluate(rec)
    assert not out.passed
    assert any(c.name == "family_office_evidenced" for c in out.failures())


def test_directory_source_cannot_verify():
    rec = _releasable(verification_sources=[
        SourceRef(source_class=SourceClass.DIRECTORY, verifies="firm type",
                  accessed_at=date(2026, 7, 27))])
    out = _gate().evaluate(rec)
    assert not out.passed
    names = {c.name for c in out.failures()}
    assert "verification_authoritative" in names and "verification_documented" in names


def test_provenance_incomplete_blocks_release():
    rec = _releasable(estimated_aum="$2B")  # populated high-value field, no provenance for it
    out = _gate().evaluate(rec)
    assert not out.passed
    assert any(c.name == "provenance_complete" for c in out.failures())


def test_missing_actionable_path_blocks_release():
    rec = _releasable(website=None, provenance={"name": _prov(SourceClass.SEC_EDGAR),
                                                "hq_country": _prov(SourceClass.SEC_EDGAR)})
    out = _gate().evaluate(rec)
    assert not out.passed
    assert any(c.name == "mandatory_fields_complete" for c in out.failures())


def test_independence_warning_blocks_release():
    # verification source class equals the discovery source class, undocumented
    rec = _releasable(discovery_source=SourceClass.FIRM_SITE)
    out = _gate().evaluate(rec)
    assert any(c.name == "no_contradictions" for c in out.failures())


# --- CORE INVARIANT ------------------------------------------------------ #

def test_rejected_value_can_never_be_shipped():
    bad = "info@wrong.example"
    audit = {"fo_1": [AuditEntry(fo_id="fo_1", field="principal_email", rejected_value=bad,
                                 reason="undeliverable", source_class=SourceClass.FIRM_SITE,
                                 checked_at=date(2026, 7, 27))]}
    # pipeline BUG: the rejected email is still sitting in the delivered field
    leaked = _releasable(principal_email=bad,
                         provenance={"name": _prov(SourceClass.SEC_EDGAR), "website": _prov(),
                                     "hq_country": _prov(SourceClass.SEC_EDGAR),
                                     "principal_email": _prov()})
    out = _gate(audit).evaluate(leaked)
    assert not out.passed
    assert any(c.name == "no_rejected_values_shipped" for c in out.failures())

    # correct pipeline: the value was removed (blanked + could_not_verify) -> gate passes G9
    fixed = _releasable(could_not_verify=["principal_email"])
    out2 = _gate(audit).evaluate(fixed)
    assert all(c.passed for c in out2.checks if c.name == "no_rejected_values_shipped")


def test_publish_returns_only_gate_approved():
    good = _releasable(fo_id="good")
    bad = _releasable(fo_id="bad", fo_type=FOType.UNDETERMINED, fo_type_evidence=None)
    released, outcomes = _gate().publish([good, bad])
    assert [r.fo_id for r in released] == ["good"]
    assert len(outcomes) == 2
