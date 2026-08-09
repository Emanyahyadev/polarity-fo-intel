"""Continuous-collection helpers: verified-contact counting and scheduling."""

from datetime import date

from fointel.operate.continuous import contact_count, is_verified_contact, planned_cycles
from fointel.schema import FamilyOfficeRecord, SourceClass, SourceRef


def _record(**over: object) -> FamilyOfficeRecord:
    base: dict = dict(fo_id="fo_t", name="Test Family Office",
                      discovery_source=SourceClass.DIRECTORY, data_as_of=date(2026, 8, 9))
    base.update(over)
    return FamilyOfficeRecord(**base)


def _verified():
    return [SourceRef(source_class=SourceClass.SEC_IAPD,
                      verifies="registration", accessed_at=date(2026, 8, 9))]


def test_not_verified_without_verification_source():
    rec = _record(verification_sources=[])
    assert not is_verified_contact(rec)


def test_not_verified_without_reachable_channel():
    rec = _record(verification_sources=_verified())
    assert not is_verified_contact(rec)


def test_verified_via_each_channel():
    for chan in ("principal_email", "principal_phone", "corporate_linkedin",
                 "principal_linkedin", "website"):
        rec = _record(verification_sources=_verified(), **{chan: "x"})
        assert is_verified_contact(rec), chan


def test_verified_contact_accepts_dicts():
    assert is_verified_contact({"verification_sources": [{}], "website": "https://x.com"})
    assert not is_verified_contact({"verification_sources": []})
    assert not is_verified_contact({"website": "https://x.com"})


def test_contact_count():
    records = [
        _record(verification_sources=_verified(), principal_email="a@b.com"),
        _record(verification_sources=_verified(), website="https://x.com"),
        _record(verification_sources=_verified()),
        _record(),
    ]
    assert contact_count(records) == 2


def test_planned_cycles_full_budget():
    assert planned_cycles(48.0, 60.0, 700, 0) == 47      # 48h / 60min, minus final sleep
    assert planned_cycles(48.0, 60.0, 700, 4) == 47


def test_planned_cycles_target_already_met_and_minimum():
    assert planned_cycles(48.0, 60.0, 700, 700) == 0
    assert planned_cycles(0.5, 60.0, 10, 0) == 1          # tiny budget -> at least one
    assert planned_cycles(48.0, 720.0, 700, 0) == 3       # 4 slots minus one