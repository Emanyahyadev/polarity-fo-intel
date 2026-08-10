"""Unit tests for page-driven person discovery — no network, synthetic HTML.

Locks in the two real bugs found and fixed during development:
  1. Free-text name matching picked up title/boilerplate fragments
     ("Compliance Officer Mr") as if they were person names.
  2. Card-boundary detection by character count let two adjacent team
     cards merge into one container, misattributing one person's email
     to another (found against a real site: Cervin Family Office).
"""

from __future__ import annotations

from src.fointel.enrichment.person_page_discovery import extract_candidates


MULTI_CARD_HTML = """
<html><body>
<nav>Home About Team Contact</nav>
<div class="grid">
  <div class="card"><h3>Jane Smith</h3><p>Founder and Chief Investment Officer.</p>
    <a href="mailto:jane@acmefo.com">Email Jane</a></div>
  <div class="card"><h3>Tom Reyes</h3><p>Managing Partner overseeing direct investments.</p>
    <a href="mailto:info@acmefo.com">general inbox (not Tom)</a></div>
  <div class="card"><h3>Ana Costa</h3><p>Head of Operations, not a decision-maker on investments.</p></div>
</div>
<p>Compliance Officer Mr. Manish Kalra can be reached regarding SEBI matters.</p>
<footer>Copyright 2026 Acme. contact@acmefo.com</footer>
</body></html>
"""


def test_verified_person_has_own_card_email():
    people = {p.name: p for p in extract_candidates(MULTI_CARD_HTML, "https://acmefo.com/team")}
    assert people["Jane Smith"].verdict == "verified_decision_maker"
    assert people["Jane Smith"].email == "jane@acmefo.com"
    assert people["Jane Smith"].title == "Founder"


def test_generic_inbox_never_counts_as_verified():
    """Real bug: a generic mailto: link correctly scoped to one person's own
    card must still not count as THEIR email."""
    people = {p.name: p for p in extract_candidates(MULTI_CARD_HTML, "https://acmefo.com/team")}
    assert people["Tom Reyes"].verdict == "possible_decision_maker"
    assert people["Tom Reyes"].email is None


def test_no_cross_card_email_leakage():
    """Real bug found against Cervin Family Office: two adjacent cards merged
    into one container let a sibling's real email attach to the wrong name."""
    people = {p.name: p for p in extract_candidates(MULTI_CARD_HTML, "https://acmefo.com/team")}
    assert people["Jane Smith"].email != people.get("Tom Reyes", people["Jane Smith"]).email \
        or people["Tom Reyes"].email is None


def test_title_boilerplate_not_treated_as_a_name():
    """Real bug: 'Compliance Officer Mr' (extracted from running prose) was
    previously accepted as a person's name."""
    names = {p.name for p in extract_candidates(MULTI_CARD_HTML, "https://acmefo.com/team")}
    assert "Compliance Officer Mr" not in names
    assert not any("compliance" in n.lower() for n in names)
    assert "Manish Kalra" not in names  # not in a heading -> correctly not extracted


def test_no_decision_maker_title_is_excluded():
    names = {p.name for p in extract_candidates(MULTI_CARD_HTML, "https://acmefo.com/team")}
    assert "Ana Costa" not in names  # "Head of Operations" is not a decision-maker title


def test_no_candidates_on_a_page_with_no_team_cards():
    html = "<html><body><p>Welcome to Acme. We manage wealth for families.</p></body></html>"
    assert extract_candidates(html, "https://acmefo.com/") == []


def test_empty_html_does_not_crash():
    assert extract_candidates("", "https://example.com/") == []
