"""Post-enrichment dedup: same firm via two lenses merges; distinct firms stay separate."""

from datetime import date

from fointel.assemble import _domain, dedupe_records
from fointel.schema import Confidence, FamilyOfficeRecord, FOType, SourceClass, SourceRef


def _rec(fo_id, name, conf, website=None, phone=None, state=None, country=None, verifies=()):
    return FamilyOfficeRecord(
        fo_id=fo_id, name=name, fo_type=FOType.MFO, fo_type_evidence="ev",
        website=website, hq_phone=phone, hq_state=state, hq_country=country,
        verification_sources=[SourceRef(source_class=sc, verifies=v, accessed_at=date(2026, 7, 27))
                              for sc, v in verifies],
        discovery_source=SourceClass.SEC_EDGAR, data_as_of=date(2026, 7, 27),
        record_confidence=conf)


def test_domain_extraction():
    assert _domain("https://www.marcuardfamilyoffice.com/") == "marcuardfamilyoffice.com"
    assert _domain("http://marcuardfamilyoffice.com/en?x=1") == "marcuardfamilyoffice.com"
    assert _domain("") == "" and _domain(None) == ""


def test_same_domain_merges_keeping_richer_record():
    # the real defect: one firm found via SEC 13F (rich) + via IAPD (thin), same website
    rich = _rec("fo_keep", "MARCUARD FAMILY OFFICE LTD", Confidence.HIGH,
                website="https://www.marcuardfamilyoffice.com/", phone="41 43 344 60 00",
                state="V8", country="Switzerland",
                verifies=[(SourceClass.SEC_EDGAR, "existence"), (SourceClass.SEC_IAPD, "registration")])
    thin = _rec("fo_drop", "MARCUARD FAMILY OFFICE LTD", Confidence.MEDIUM,
                website="https://marcuardfamilyoffice.com/", country="Switzerland",
                verifies=[(SourceClass.FIRM_SITE, "family-office status")])

    kept, decisions = dedupe_records([rich, thin])
    assert len(kept) == 1
    assert kept[0].fo_id == "fo_keep"                       # richer record kept
    assert kept[0].hq_phone == "41 43 344 60 00"
    # union of verification sources across both records
    classes = {s.source_class for s in kept[0].verification_sources}
    assert {SourceClass.SEC_EDGAR, SourceClass.SEC_IAPD, SourceClass.FIRM_SITE} <= classes
    assert len(decisions) == 1 and decisions[0]["basis"].startswith("domain:")


def test_distinct_firms_are_not_merged():
    a = _rec("a", "Alpha Family Office", Confidence.HIGH, website="https://alpha-fo.com/", country="United States")
    b = _rec("b", "Beta Family Office", Confidence.HIGH, website="https://beta-fo.com/", country="United States")
    kept, decisions = dedupe_records([a, b])
    assert len(kept) == 2 and decisions == []


def test_same_name_different_geography_not_merged():
    # conservative: identical normalised name but different states stays distinct (D14)
    a = _rec("a", "Standard Family Office LLC", Confidence.HIGH, state="SD", country="United States")
    b = _rec("b", "Standard Family Office LLC", Confidence.MEDIUM, state="NY", country="United States")
    kept, _ = dedupe_records([a, b])
    assert len(kept) == 2
