"""Field-level completeness and dataset coverage — the quality-over-quantity
contract: only records satisfying the full release policy count toward a target,
nothing is ever counted merely because it exists."""

from datetime import date

import pytest

from fointel.schema import (Confidence, EmailStatus, FamilyOfficeRecord, FOType,
                            Provenance, SourceClass, SourceRef)
from fointel.validation.completeness import (dataset_coverage, gate_passing_count,
                                             record_completeness)

AS_OF = date(2026, 8, 9)
TODAY = date(2026, 8, 10)


def _prov(field_source: str = "SEC EDGAR", conf: Confidence = Confidence.HIGH):
    return Provenance(source_class=SourceClass.SEC_EDGAR, method=field_source,
                      checked_at=AS_OF, confidence=conf)


def _ref(sc: SourceClass = SourceClass.SEC_IAPD):
    return SourceRef(source_class=sc, verifies="firm registration",
                     accessed_at=AS_OF)


def _rec(**over: object) -> FamilyOfficeRecord:
    base: dict = dict(
        fo_id="fo_test", name="Test Family Office", fo_type=FOType.SFO,
        fo_type_evidence="registrant self-identifies as a family office",
        fo_type_confidence=Confidence.HIGH, discovery_source=SourceClass.SEC_EDGAR,
        verification_sources=[_ref()], data_as_of=AS_OF,
        provenance={"name": _prov(), "fo_type": _prov(), "hq_country": _prov(),
                    "website": _prov("firm website", Confidence.MEDIUM),
                    "fo_type_evidence": _prov(),
                    "principal_name": _prov(),
                    "principal_email": _prov("firm website", Confidence.MEDIUM),
                    "estimated_aum": _prov()},
        hq_country="United States", website="https://testfamilyoffice.com",
        principal_name="Jane Smith", principal_email="jane@testfamilyoffice.com",
        principal_email_status=EmailStatus.DELIVERABLE,
        estimated_aum="$100.0M in 13(f) securities as of 03-31-2026 (SEC Form 13F)")
    base.update(over)
    return FamilyOfficeRecord(**base)


# ------------------------------------------------------------ per record - #
def test_complete_record_is_fully_enriched_and_releasable():
    c = record_completeness(_rec())
    assert c["required_fields_complete"]
    assert c["fully_enriched"]
    assert c["release_status"] == "releasable"
    assert c["validation_status"] == "passed"
    assert c["verified_fields"] and "principal_name" in c["verified_fields"]
    assert c["missing_fields"] == []


def test_missing_geography_blocks_release():
    c = record_completeness(_rec(hq_country=None))
    assert "geography" in c["missing_fields"]
    assert not c["required_fields_complete"]
    assert c["release_status"] == "blocked"


def test_populated_without_provenance_is_unverified_never_counted():
    rec = _rec()
    rec.website = "https://hello.fake-domain.io"
    del rec.provenance["website"]
    c = record_completeness(rec)
    assert "website" in c["unverified_fields"]
    assert "website" not in c["verified_fields"]
    assert c["release_status"] == "blocked"          # G8 provenance gate


def test_low_provenance_never_verified():
    rec = _rec()
    rec.principal_name = "Jane Smith"
    rec.provenance["principal_name"] = _prov("low", Confidence.LOW)
    c = record_completeness(rec)
    assert "principal_name" in c["unverified_fields"]
    assert "principal_name" not in c["verified_fields"]


def test_undetermined_type_without_evidence_is_honest_but_counted_per_gates():
    rec = _rec(fo_type=FOType.UNDETERMINED, fo_type_evidence=None,
               fo_type_confidence=Confidence.LOW,
               provenance={"name": _prov(), "hq_country": _prov(),
                           "website": _prov("firm website", Confidence.MEDIUM)})
    c = record_completeness(rec)
    assert c["classification_status"] == "Undetermined"
    assert "fo_type_evidence" in c["missing_fields"]


# ------------------------------------------------------------ dataset - #
def test_gate_passing_count_only_counts_policy_satisfying_records():
    good = _rec()
    no_geo = _rec(fo_id="fo_no_geo", hq_country=None)
    no_prov = _rec(fo_id="fo_no_prov")
    no_prov.website = "https://fake.example.com"
    del no_prov.provenance["website"]
    assert gate_passing_count([good, no_geo, no_prov]) == 1


def test_dataset_coverage_metrics_and_contact_verification():
    good = _rec()
    risky = _rec(fo_id="fo_risky", principal_email="info@risky.com",
                 principal_email_status=EmailStatus.RISKY, estimated_aum=None)
    risky.provenance["principal_email"] = _prov("firm website", Confidence.MEDIUM)
    risky.provenance.pop("estimated_aum", None)
    poor = _rec(fo_id="fo_poor", hq_country=None, principal_name=None,
                principal_email=None, estimated_aum=None)
    for f in ("principal_name", "principal_email", "estimated_aum"):
        poor.provenance.pop(f, None)

    cov = dataset_coverage([good, risky, poor])
    assert cov["total_records"] == 3
    assert cov["released_records"] == 2                # poor is blocked (G7)
    assert cov["evidence_coverage"] == 1.0             # all have authoritative sources
    assert cov["named_person_coverage"] == pytest.approx(2 / 3, abs=0.001)
    assert cov["verified_contact_coverage"] == pytest.approx(1 / 3, abs=0.001)   # only DELIVERABLE email counts
    assert cov["classification_distribution"]["Single-Family Office"] == 3
    assert cov["required_field_completion_rate"] == pytest.approx(2 / 3, abs=0.001)
    assert cov["fully_enriched"] == 2            # good + risky carry verified intel
    assert not record_completeness(poor)["fully_enriched"]


def test_empty_coverage_is_empty_not_fabricated():
    cov = dataset_coverage([])
    assert cov["total_records"] == 0 and cov["released_records"] == 0
    assert cov["classification_distribution"] == {}