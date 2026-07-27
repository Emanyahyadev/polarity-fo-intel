"""IAPD / Form ADV parsing (no network)."""

from fointel.enrichment.iapd import IapdEnricher


def _src(**over) -> dict:
    base = {
        "firm_source_id": 151736, "firm_ia_full_sec_number": "801-70776", "firm_name": "PATHSTONE",
        "firm_other_names": ["PATHSTONE", "STONE TOWER FAMILY OFFICE, LLC",
                             "PATHSTONE FAMILY OFFICE, LLC"],
        "firm_ia_scope": "ACTIVE",
        "firm_ia_address_details": ('{"officeAddress": {"street1": "10 STERLING BLVD", '
                                    '"city": "ENGLEWOOD", "state": "NJ", "country": "United States"}}'),
    }
    base.update(over)
    return base


def test_parse_detects_family_office_alias_and_address():
    f = IapdEnricher._parse(_src())
    assert f.crd == "151736" and f.sec_number == "801-70776"
    assert f.fo_language is True            # a registered alias says "family office"
    assert f.city == "ENGLEWOOD" and f.state == "NJ" and f.country == "United States"
    assert f.active is True


def test_parse_resolves_single_family_type():
    f = IapdEnricher._parse(_src(firm_other_names=["ACME SINGLE FAMILY OFFICE LLC"]))
    assert f.fo_language is True and f.fo_type_hint == "SFO"


def test_parse_non_family_office_firm():
    f = IapdEnricher._parse(_src(firm_name="KRAMER CAPITAL MANAGEMENT LLC",
                                 firm_other_names=["KRAMER CAPITAL MANAGEMENT LLC"]))
    assert f.fo_language is False and f.fo_type_hint is None
