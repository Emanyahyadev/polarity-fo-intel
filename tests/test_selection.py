"""Final-selection policy: per-source cap, justified relaxation, quality ordering."""

from datetime import date

from fointel.schema import Confidence, FamilyOfficeRecord, FOType, SourceClass
from fointel.validation.selection import select_final


def _rec(i, source, conf=Confidence.MEDIUM) -> FamilyOfficeRecord:
    return FamilyOfficeRecord(
        fo_id=f"fo_{i}", name=f"FO {i}", fo_type=FOType.SFO, fo_type_evidence="ev",
        discovery_source=source, record_confidence=conf, data_as_of=date(2026, 7, 27))


def test_no_source_exceeds_cap_when_diversity_is_available():
    recs = ([_rec(f"s{i}", SourceClass.SEC_EDGAR) for i in range(20)]
            + [_rec(f"d{i}", SourceClass.DIRECTORY) for i in range(20)]
            + [_rec(f"i{i}", SourceClass.IRS_990PF) for i in range(20)])
    selected, report = select_final(recs, target=10, max_share=0.4)  # cap = 4
    assert report["selected"] == 10
    assert max(report["source_counts"].values()) <= 4
    assert not report["cap_relaxed"]


def test_cap_relaxes_only_with_justification_when_insufficient_diversity():
    recs = [_rec(f"s{i}", SourceClass.SEC_EDGAR) for i in range(10)]  # single source
    selected, report = select_final(recs, target=10, max_share=0.4)  # cap = 4
    assert report["selected"] == 10
    assert report["cap_relaxed"] is True
    assert report["justification"]                                   # non-empty reason logged
    assert report["source_counts"][SourceClass.SEC_EDGAR.value] == 10


def test_quality_ordering_prefers_higher_confidence_within_source():
    recs = [_rec("low1", SourceClass.SEC_EDGAR, Confidence.LOW),
            _rec("high", SourceClass.SEC_EDGAR, Confidence.HIGH),
            _rec("low2", SourceClass.SEC_EDGAR, Confidence.LOW)]
    selected, _ = select_final(recs, target=1, max_share=1.0)
    assert selected[0].fo_id == "fo_high"


def test_returns_all_when_fewer_than_target():
    recs = [_rec(1, SourceClass.SEC_EDGAR), _rec(2, SourceClass.DIRECTORY)]
    selected, report = select_final(recs, target=50)
    assert report["selected"] == 2 and len(selected) == 2
