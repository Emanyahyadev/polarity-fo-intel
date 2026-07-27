"""SEC enrichment parser + formatters (no network)."""

from fointel.enrichment.sec import SecEnricher, _format_ein, _format_phone


def test_phone_formatting():
    assert _format_phone("9543859624") == "+1 (954) 385-9624"
    assert _format_phone("1-954-385-9624") == "+1 (954) 385-9624"
    assert _format_phone(None) is None
    assert _format_phone("+44 20 1234 5678") == "+44 20 1234 5678"  # non-US kept as-is


def test_ein_formatting_and_placeholder():
    assert _format_ein("821622734") == "82-1622734"
    assert _format_ein("99-9999999") is None      # SEC placeholder
    assert _format_ein("999999999") is None
    assert _format_ein(None) is None


def _submissions(**over) -> dict:
    base = {
        "name": "EMFO, LLC", "ein": "821622734", "website": "", "entityType": "other",
        "sic": "", "sicDescription": "", "tickers": [], "exchanges": [],
        "addresses": {"business": {"street1": "2700 S COMMERCE PARKWAY", "city": "WESTON",
                                   "stateOrCountry": "FL", "zipCode": "33331",
                                   "stateOrCountryDescription": "FL"}},
        "phone": "9543859624", "formerNames": [],
        "filings": {"recent": {"form": ["13F-HR", "13F-HR", "N-PX"]}},
    }
    base.update(over)
    return base


def test_parse_us_firm():
    f = SecEnricher._parse("0001859434", _submissions())
    assert f.legal_name == "EMFO, LLC"
    assert f.city == "WESTON" and f.state == "FL" and f.country == "United States"
    assert f.phone == "+1 (954) 385-9624"
    assert f.ein == "82-1622734"
    assert f.is_public_company is False
    assert f.forms_filed == ["13F-HR", "N-PX"]     # deduped + sorted


def test_public_company_is_flagged():
    f = SecEnricher._parse("1", _submissions(tickers=["MSGE"], exchanges=["NYSE"]))
    assert f.is_public_company is True


def test_foreign_location_uses_country_description():
    subs = _submissions(addresses={"business": {"city": "London", "stateOrCountry": "X0",
                                                "stateOrCountryDescription": "United Kingdom"}})
    f = SecEnricher._parse("2", subs)
    assert f.country == "United Kingdom" and f.state is None
