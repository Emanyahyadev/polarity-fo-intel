"""Website text analysis (no I/O): FO-language detection, SFO/MFO hint, AUM extraction."""

from fointel.enrichment.website import analyze_text


def test_detects_single_family_office():
    fo, hint, aum = analyze_text("We are a single-family office serving the Smith family.")
    assert fo is True and hint == "SFO"


def test_detects_multi_family_office_and_aum():
    fo, hint, aum = analyze_text(
        "A modern multi-family office managing over $5 billion in assets under management.")
    assert fo is True and hint == "MFO"
    assert aum == "$5 billion"


def test_no_family_office_language():
    fo, hint, aum = analyze_text("We are a global asset management firm.")
    assert fo is False and hint is None and aum is None


def test_aum_alternate_phrasing():
    _, _, aum = analyze_text("The firm oversees $2.3 billion for a single family.")
    assert aum == "$2.3 billion"
