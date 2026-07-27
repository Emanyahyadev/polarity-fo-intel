"""Unit tests for discovery pure-functions (no network): name cleaning, extraction, dedup."""

from fointel.discovery.news import _extract_fo_names
from fointel.discovery.sec_edgar import _clean_name
from fointel.text import norm_name


def test_sec_clean_name_strips_cik_suffix():
    assert _clean_name("EMFO, LLC  (CIK 0001859434)") == "EMFO, LLC"
    assert _clean_name("Duquesne Family Office LLC (CIK 1541617)") == "Duquesne Family Office LLC"
    assert _clean_name("Plain Name") == "Plain Name"


def test_news_extracts_named_family_offices_only():
    got = _extract_fo_names("The Smith Family Office backed a startup this week")
    assert "Smith Family Office" in got
    # a generic 'family office' with a stopword head must NOT become a candidate
    assert _extract_fo_names("How a family office invests in private equity") == set()


def test_norm_name_collapses_entity_variants():
    assert norm_name("The Smith Family Office, LLC") == norm_name("Smith Family Office")
    assert norm_name("Duquesne Family Office LLC") == norm_name("Duquesne")
