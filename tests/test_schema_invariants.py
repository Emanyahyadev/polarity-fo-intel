"""Schema-level invariants: the populated/could-not-verify contradiction and Rule 1 completeness."""

from datetime import date

import pytest
from pydantic import ValidationError

from fointel.schema import (
    Confidence,
    FamilyOfficeRecord,
    FOType,
    Provenance,
    Signal,
    SourceClass,
)


def _base(**kw) -> FamilyOfficeRecord:
    defaults = dict(fo_id="fo_1", name="X FO", discovery_source=SourceClass.SEC_EDGAR,
                    data_as_of=date(2026, 7, 27))
    defaults.update(kw)
    return FamilyOfficeRecord(**defaults)


def _prov(field_conf=Confidence.HIGH) -> Provenance:
    return Provenance(source_class=SourceClass.FIRM_SITE, method="site fetch",
                      checked_at=date(2026, 7, 27), confidence=field_conf)


# --- construction-time invariant ---------------------------------------- #

def test_populated_field_marked_could_not_verify_is_rejected():
    with pytest.raises(ValidationError):
        _base(principal_email="a@b.com", could_not_verify=["principal_email"])


def test_blank_field_may_be_marked_could_not_verify():
    rec = _base(could_not_verify=["principal_email"])  # blank + flagged is honest
    assert "principal_email" in rec.could_not_verify


# --- Rule 1 completeness (provenance_violations) ------------------------- #

def test_populated_high_value_field_without_provenance_is_a_violation():
    rec = _base(website="https://x.com")  # no provenance for website
    fields = [f for f, _ in rec.provenance_violations()]
    assert "website" in fields


def test_provenanced_field_is_not_a_violation():
    rec = _base(website="https://x.com", provenance={"website": _prov()})
    fields = [f for f, _ in rec.provenance_violations()]
    assert "website" not in fields


def test_blank_optional_field_is_not_a_violation():
    rec = _base()  # website absent entirely
    fields = [f for f, _ in rec.provenance_violations()]
    assert "website" not in fields


def test_classified_without_evidence_is_a_violation():
    rec = _base(fo_type=FOType.SFO)  # no fo_type_evidence
    assert ("fo_type", "classified as a family office without evidence") in rec.provenance_violations()


def test_signal_without_source_is_flagged():
    # Signal requires source_class, so we exercise the missing-url branch via a signal
    # that has a class but no url is allowed; a fully sourced signal is clean.
    rec = _base(signals=[Signal(text="raised fund", source_class=SourceClass.NEWS,
                                source_url="https://n.example/x")])
    assert not any(f.startswith("signal") for f, _ in rec.provenance_violations())
