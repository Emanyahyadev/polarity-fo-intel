"""Signals enrichment: GDELT date parsing (no network)."""

from datetime import date

from fointel.enrichment.signals import _parse_gdelt_date


def test_parse_gdelt_date():
    assert _parse_gdelt_date("20260727T091500Z") == date(2026, 7, 27)
    assert _parse_gdelt_date("20251231T000000Z") == date(2025, 12, 31)


def test_parse_gdelt_date_handles_bad_input():
    assert _parse_gdelt_date(None) is None
    assert _parse_gdelt_date("") is None
    assert _parse_gdelt_date("garbage") is None
