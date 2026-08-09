"""Contact intelligence: website extraction + build_record wiring.

Guarantees the Stage-2 promise: emails and LinkedIn URLs are filled WHERE the
firm's official site actually publishes them (with provenance, status=risky for
a firm mailbox) and honestly blank + could_not_verify otherwise. Never guessed.
"""

from datetime import date

from fointel.assemble import EnrichedFirm, build_record
from fointel.discovery.base import Candidate
from fointel.enrichment.website import WebsiteEnricher, WebsiteFacts, extract_contacts
from fointel.schema import Confidence, EmailStatus, FOType, SourceClass
from fointel.validation.firm_type import Classification

AS_OF = date(2026, 8, 9)


def _candidate() -> Candidate:
    return Candidate(name="Smith Family Office", source_class=SourceClass.DIRECTORY,
                     source_url="https://smithfamilyoffice.com",
                     identifiers={"qid": "Q123"}, raw={}, hints={})


def _enriched(wf: WebsiteFacts) -> EnrichedFirm:
    cls = Classification(fo_type=FOType.SFO,
                         evidence="site states it is a single-family office",
                         confidence=Confidence.HIGH, qualifies=True)
    return EnrichedFirm(candidate=_candidate(), website=wf.url, website_facts=wf,
                        classification=cls)


# ---------------------------------------------------------------- extraction - #
def test_extract_contacts_prefers_role_inbox_filters_junk():
    text = ("""
    <a href="mailto:info@smithfamilyoffice.com">Email us</a>
    Reach the team at office@smithfamilyoffice.com or on LinkedIn:
    https://www.linkedin.com/company/smith-family-office
    junk: no-reply@smithfamilyoffice.com, pixel@tracking.io,
    newsletter@wixpress.com, contact@example.com, hello@cdn.smithfamilyoffice.com
    """)
    emails, linkedin = extract_contacts(text, "https://www.smithfamilyoffice.com")
    assert emails[0] == "info@smithfamilyoffice.com"
    assert "office@smithfamilyoffice.com" in emails
    assert "hello@cdn.smithfamilyoffice.com" in emails        # own subdomain is fine
    assert all("noreply" not in e and "wixpress" not in e for e in emails)
    assert all(e.rsplit("@", 1)[1] == "smithfamilyoffice.com"
               or e.rsplit("@", 1)[1].endswith(".smithfamilyoffice.com") for e in emails)
    assert linkedin == "https://www.linkedin.com/company/smith-family-office"


def test_extract_contacts_drops_foreign_domains():
    text = ("info@smithfamilyoffice.com and the hosting vendor hello@webhost.io "
            "and a newsletter via news@substack.com")
    emails, linkedin = extract_contacts(text, "https://smithfamilyoffice.com")
    assert emails == ["info@smithfamilyoffice.com"]
    assert linkedin is None


def test_extract_contacts_linkedin_ignores_junk_slugs():
    text = ("linkedin.com/company/careers linkedin.com/pages/company/smith-family-office "
            "linkedin.com/showcase/investors")
    emails, linkedin = extract_contacts(text, "https://smithfamilyoffice.com")
    assert linkedin == "https://www.linkedin.com/company/smith-family-office"


def test_website_facts_defaults_back_compat():
    wf = WebsiteFacts(url="https://x.com", resolved=True)
    assert wf.emails == [] and wf.linkedin is None


# ------------------------------------------------------------------- wiring - #
def test_build_record_wires_site_contacts_with_provenance():
    wf = WebsiteFacts(url="https://smithfamilyoffice.com", resolved=True,
                      fo_language=True, emails=["info@smithfamilyoffice.com"],
                      linkedin="https://www.linkedin.com/company/smith-family-office")
    rec = build_record(_enriched(wf), AS_OF)
    assert rec is not None
    assert rec.principal_email == "info@smithfamilyoffice.com"
    assert rec.principal_email_status == EmailStatus.RISKY
    assert "contact" in rec.provenance["principal_email"].method
    assert rec.corporate_linkedin == "https://www.linkedin.com/company/smith-family-office"
    assert "LinkedIn" in rec.provenance["corporate_linkedin"].method
    assert "principal_email" not in rec.could_not_verify
    assert "corporate_linkedin" not in rec.could_not_verify
    assert rec.provenance_violations() == []
    assert "principal's personally-verified" in rec.reviewer_notes


def test_build_record_keeps_stage1_honesty_when_site_publishes_nothing():
    wf = WebsiteFacts(url="https://smithfamilyoffice.com", resolved=True, fo_language=True)
    rec = build_record(_enriched(wf), AS_OF)
    assert rec is not None
    assert rec.principal_email is None
    assert rec.corporate_linkedin is None
    assert "principal_email" in rec.could_not_verify
    assert "corporate_linkedin" in rec.could_not_verify
    assert rec.provenance_violations() == []


def test_delivery_row_carries_contact_columns():
    wf = WebsiteFacts(url="https://smithfamilyoffice.com", resolved=True, fo_language=True,
                      emails=["info@smithfamilyoffice.com"])
    rec = build_record(_enriched(wf), AS_OF)
    row = rec.to_delivery_row()
    assert row["principal_email"] == "info@smithfamilyoffice.com"
    assert row["principal_email_status"] == "risky"


# -------------------------------------------------------------- deep fetch - #
def test_fetch_site_deep_hits_contact_page_when_homepage_has_no_contacts(monkeypatch):
    enr = WebsiteEnricher()

    def fake_fetch(self, url):
        if url == "https://smithfamilyoffice.com":
            return WebsiteFacts(url=url, resolved=True, fo_language=True), None
        if url == "https://smithfamilyoffice.com/contact":
            return (WebsiteFacts(url=url, resolved=True, fo_language=True,
                                 emails=["info@smithfamilyoffice.com"]), None)
        return WebsiteFacts(url=url, resolved=False), None

    monkeypatch.setattr(enr, "fetch_site", fake_fetch.__get__(enr, WebsiteEnricher))
    facts, refs = enr.fetch_site_deep("https://smithfamilyoffice.com")
    assert facts.emails == ["info@smithfamilyoffice.com"]
    assert facts.fo_language