"""Unit tests for the core data model, the two rules of proof, and field-level confidence."""

from datetime import date

from fointel.schema import (
    AuditEntry,
    Confidence,
    FamilyOfficeRecord,
    FOType,
    Provenance,
    Signal,
    SourceClass,
    SourceRef,
)


def _base(**kw) -> FamilyOfficeRecord:
    defaults = dict(
        fo_id="fo_0001",
        name="Test Family Office",
        discovery_source=SourceClass.IRS_990PF,
        data_as_of=date(2026, 7, 27),
    )
    defaults.update(kw)
    return FamilyOfficeRecord(**defaults)


# --- Rule 2: firm-level proof --------------------------------------------- #

def test_undetermined_does_not_qualify():
    assert _base(fo_type=FOType.UNDETERMINED).qualifies() is False


def test_type_without_evidence_does_not_qualify():
    assert _base(fo_type=FOType.SFO).qualifies() is False


def test_evidenced_sfo_qualifies():
    rec = _base(fo_type=FOType.SFO, fo_type_evidence="990-PF names a single family as sole donor")
    assert rec.qualifies() is True


# --- Field-level confidence ----------------------------------------------- #

def test_field_confidence_reads_provenance():
    rec = _base(
        website="https://x.com",
        provenance={"website": Provenance(
            source_class=SourceClass.FIRM_SITE, method="resolved 200",
            checked_at=date(2026, 7, 27), confidence=Confidence.HIGH)},
    )
    assert rec.field_confidence("website") == Confidence.HIGH
    assert rec.field_confidence("principal_email") is None  # no basis -> no confidence


def test_recent_activity_confidence_is_weakest_link():
    rec = _base(signals=[
        Signal(text="a", source_class=SourceClass.NEWS, confidence=Confidence.HIGH),
        Signal(text="b", source_class=SourceClass.NEWS, confidence=Confidence.LOW),
    ])
    assert rec.field_confidence("recent_activity") == Confidence.LOW


def test_record_confidence_falls_with_weak_anchor():
    strong = _base(
        fo_type=FOType.SFO, fo_type_evidence="ev", fo_type_confidence=Confidence.HIGH,
        provenance={"name": Provenance(source_class=SourceClass.SEC_ADV, method="ADV Item 1",
                                       checked_at=date(2026, 7, 27), confidence=Confidence.HIGH)},
    )
    assert strong.compute_record_confidence() == Confidence.HIGH
    weak = _base(fo_type=FOType.SFO, fo_type_evidence="ev", fo_type_confidence=Confidence.LOW)
    assert weak.compute_record_confidence() == Confidence.LOW


# --- Discovery / verification separation ---------------------------------- #

def test_independence_warning_when_verify_equals_discovery():
    rec = _base(
        discovery_source=SourceClass.NEWS,
        verification_sources=[SourceRef(source_class=SourceClass.NEWS, verifies="principal name",
                                        accessed_at=date(2026, 7, 27))],
    )
    assert rec.independence_warnings()  # non-empty -> flagged
    documented = _base(
        discovery_source=SourceClass.NEWS,
        reviewer_notes="same-source use justified: two independent articles",
        verification_sources=[SourceRef(source_class=SourceClass.NEWS, verifies="principal name",
                                        accessed_at=date(2026, 7, 27))],
    )
    assert not documented.independence_warnings()


# --- Emission -------------------------------------------------------------- #

def test_delivery_row_has_confidence_and_verification_columns():
    rec = _base(
        fo_type=FOType.MFO,
        fo_type_evidence="website states it serves multiple families",
        fo_type_confidence=Confidence.HIGH,
        signals=[Signal(text="Committed to Fund X", source_class=SourceClass.NEWS,
                        event_date=date(2026, 6, 1))],
        verification_sources=[SourceRef(source_class=SourceClass.FIRM_SITE,
                                        verifies="firm type, principal",
                                        accessed_at=date(2026, 7, 27), url="https://x.com")],
    )
    row = rec.to_delivery_row(max_signals=3)
    assert row["family_office_name"] == "Test Family Office"
    assert row["recent_signal_1"] == "Committed to Fund X"
    assert row["recent_signal_2"] == ""              # padded
    assert row["fo_type_confidence"] == "High"       # field-level confidence column
    assert "Firm Website" in row["verification_sources"]
    assert row["discovery_source"] == "IRS 990-PF (ProPublica Nonprofit Explorer)"


def test_source_rows_separate_discovery_and_verification():
    rec = _base(
        discovery_source=SourceClass.IRS_990PF,
        verification_sources=[SourceRef(source_class=SourceClass.FIRM_SITE, verifies="website",
                                        accessed_at=date(2026, 7, 27))],
    )
    roles = {r["role"] for r in rec.source_rows()}
    assert roles == {"discovery", "verification"}


def test_audit_entry_records_withheld_value():
    a = AuditEntry(fo_id="fo_0001", field="principal_email", rejected_value="bad@x.com",
                   reason="undeliverable (SMTP 550)", source_class=SourceClass.FIRM_SITE,
                   checked_at=date(2026, 7, 27))
    assert a.reason.startswith("undeliverable")
