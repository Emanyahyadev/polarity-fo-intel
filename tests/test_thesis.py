"""Investment-thesis extraction: keep real prose statements, reject navigation menus."""

from fointel.enrichment.website import extract_thesis, _looks_like_prose


def test_extracts_real_thesis_sentence():
    text = ("Home About Contact. We believe wealth should enhance your life and support "
            "your purpose. Learn more.")
    assert extract_thesis(text) == "We believe wealth should enhance your life and support your purpose."


def test_rejects_navigation_menu_as_thesis():
    nav = ("Our Team Our Services Wealth Planning Investment Management Fiduciary Services "
           "Contact Us News Insights Home About Our Values Why Us")
    assert _looks_like_prose(nav) is False
    assert extract_thesis(nav) is None


def test_none_when_no_statement():
    assert extract_thesis("Home. Contact. Login. Cookie policy.") is None


def test_prose_needs_lowercase_connectives():
    # a mixed prose sentence with connectives passes; a title-case run does not
    assert _looks_like_prose("We partner with families to preserve and grow their capital.") is True
    assert _looks_like_prose("Wealth Planning Investment Management Fiduciary Services Team") is False
