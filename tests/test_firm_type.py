"""Firm-type classification (Rule 2) against the inclusion standard."""

from fointel.enrichment.sec import SecFacts
from fointel.schema import Confidence, FOType
from fointel.validation.firm_type import classify


def _sec(**kw) -> SecFacts:
    base = dict(cik="1", is_public_company=False)
    base.update(kw)
    return SecFacts(**base)


def test_public_company_rejected():
    c = classify("Madison Square Garden Entertainment Corp", sec_facts=_sec(is_public_company=True))
    assert not c.qualifies and "public company" in c.reject_reason


def test_individual_trustee_rejected():
    c = classify("HALL LAURIE J TRUSTEE", sec_facts=_sec())
    assert not c.qualifies and "trustee" in c.reject_reason


def test_education_network_rejected_despite_family_office_name():
    # has 'family office' in the name but is an education/network org -> must be rejected
    c = classify("Family Office University Network")
    assert not c.qualifies and c.reject_reason


def test_religious_org_rejected():
    c = classify("Vincentian Family Office")
    assert not c.qualifies and "religious" in c.reject_reason


def test_name_alone_without_authoritative_source_does_not_qualify():
    # a directory-only candidate: 'family office' in name but no SEC filing, no website
    c = classify("Walton Family Office")
    assert not c.qualifies and "no affirmative" in c.reject_reason


def test_sec_family_office_filer_qualifies_medium_undetermined():
    c = classify("EMFO Family Office LLC", sec_facts=_sec())
    assert c.qualifies
    assert c.confidence == Confidence.MEDIUM
    assert c.fo_type == FOType.UNDETERMINED       # single vs multi not established
    assert "SEC 13F filer" in c.evidence


def test_website_corroboration_raises_to_high_and_resolves_sfo():
    c = classify("Duquesne Family Office LLC", sec_facts=_sec(),
                 website_text="Duquesne is a single-family office serving the Druckenmiller family.")
    assert c.qualifies
    assert c.confidence == Confidence.HIGH        # SEC + website = two sources
    assert c.fo_type == FOType.SFO


def test_multi_family_language_sets_mfo():
    c = classify("Pathstone Family Office", sec_facts=_sec(),
                 website_text="Pathstone is a modern multi-family office.")
    assert c.qualifies and c.fo_type == FOType.MFO
