"""Named-person contact enrichment: only name-matched evidence counts (Target 3).

Never a pattern guess (no firstname.lastname@domain generation); a generic
inbox or an unrelated colleague's card must never be attached to the principal.
"""

from fointel.enrichment.person_contact import _extract_from_page, same_person


def test_extract_from_page_finds_name_matched_email_and_linkedin():
    html = """
    <div class="team">
      <div class="card">
        <h3>Jane A. Smith</h3>
        <p>Chief Investment Officer</p>
        <p>jane@smithfamilyoffice.com</p>
        <a href="https://www.linkedin.com/in/jane-smith-cio">LinkedIn</a>
      </div>
      <div class="card">
        <h3>Bob Jones</h3>
        <p>Operations</p>
        <p>bob@smithfamilyoffice.com</p>
      </div>
    </div>
    """
    facts = _extract_from_page(html, "https://smithfamilyoffice.com/team", "Jane Smith")
    assert facts is not None
    assert facts.found is True
    assert facts.email == "jane@smithfamilyoffice.com"
    assert facts.linkedin == "https://www.linkedin.com/in/jane-smith-cio"
    assert "Jane Smith" in facts.matched_name or "Jane A. Smith" in facts.matched_name
    # must NOT pick up the other team member's card
    assert facts.email != "bob@smithfamilyoffice.com"


def test_extract_from_page_ignores_company_linkedin_and_foreign_domain():
    html = """
    <div class="card">
      <h3>Jane Smith</h3>
      <a href="https://www.linkedin.com/company/smith-family-office">Company page</a>
      <p>jane@vendor-crm.io</p>
    </div>
    """
    facts = _extract_from_page(html, "https://smithfamilyoffice.com/team", "Jane Smith")
    assert facts is None  # no /in/ profile, no on-domain email -> honest non-match


def test_extract_from_page_no_name_present_returns_none():
    html = "<div class='card'><h3>Someone Else</h3><p>hi@smithfamilyoffice.com</p></div>"
    facts = _extract_from_page(html, "https://smithfamilyoffice.com/team", "Jane Smith")
    assert facts is None


def test_same_person():
    assert same_person("Jane Smith", "Jane A. Smith")
    assert same_person("Jane A. Smith, CFA", "Jane Smith")
    assert not same_person("Jane Smith", "Bob Jones")
    assert not same_person("Jane Smith", None)
    assert not same_person(None, None)
