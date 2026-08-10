"""
Named-person contact enrichment — the genuine principal_email/principal_linkedin
path (Stage 2 Target 3).

Distinct from website.py's generic-inbox capture (firm_contact_email): this module
only ever returns a contact when the evidence NAME-MATCHES a specific person. A
firm's team/about/people page is fetched and scanned for a "card" (a DOM element —
div/li/tr/article/p) that contains BOTH the principal's name AND a personal
LinkedIn profile (`/in/...`, never `/company/...`) and/or an email on the firm's
own domain adjacent to that name. No pattern is ever generated
(firstname.lastname@domain); an email/LinkedIn only counts if it was literally
printed next to the person's name on the firm's own page.

If the firm publishes no team page, or publishes one with no name-adjacent
contact, this returns PersonContactFacts(found=False, ...) — a real, honest
negative, not an error and not a guess.
"""

from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup
from pydantic import BaseModel

from ..evidence import EvidenceRef
from ..http import HttpClient
from ..observability import get_logger
from .website import _BAD_MAIL, _EMAIL_RE, _site_domain

log = get_logger("enrichment")

_TEAM_PATHS = ("team", "our-team", "people", "leadership", "about/team", "about-us/team")

# a personal LinkedIn profile, NOT a company page
_LINKEDIN_PERSON_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/([A-Za-z0-9_\-%]+)", re.IGNORECASE)

# tags likely to be one "card"/row for a single team member
_CARD_TAGS = ("div", "li", "article", "tr", "section", "p")


def _name_pattern(name: str) -> Optional[re.Pattern]:
    """First-name ... last-name pattern, tolerant of a middle name/initial or a
    trailing credential the PAGE adds that the filed name doesn't have (and vice
    versa) — e.g. filed 'Jane Smith' still matches page text 'Jane A. Smith, CFA'."""
    parts = [re.escape(p) for p in re.split(r"\s+", name.strip()) if p]
    if len(parts) < 2:
        return re.compile(re.escape(name.strip()), re.IGNORECASE) if len(name.strip()) >= 5 else None
    first, last = parts[0], parts[-1]
    return re.compile(rf"\b{first}\b(?:\s+\S+){{0,2}}?\s+\b{last}\b", re.IGNORECASE)


def _clean_name(name: str) -> list[str]:
    """Tokenize a name, dropping a trailing ', CFA'-style credential suffix and
    punctuation, so 'Jane A. Smith, CFA' compares equal to 'Jane Smith'."""
    head = name.split(",")[0]
    return [re.sub(r"[.,]", "", p).lower() for p in re.split(r"\s+", head.strip()) if p]


def same_person(a: Optional[str], b: Optional[str]) -> bool:
    """True if two name strings plausibly name the same person (first+last token
    match, case-insensitive). Used to guard against attaching a contact matched to
    one person's name onto a DIFFERENT person's record when the authoritative
    principal (e.g. ADV owner) differs from who the page search was seeded with
    (e.g. a 13F signatory)."""
    if not a or not b:
        return False
    pa, pb = _clean_name(a), _clean_name(b)
    if len(pa) < 2 or len(pb) < 2:
        return pa == pb
    return pa[0] == pb[0] and pa[-1] == pb[-1]


class PersonContactFacts(BaseModel):
    found: bool = False
    matched_name: Optional[str] = None
    email: Optional[str] = None
    linkedin: Optional[str] = None
    source_url: Optional[str] = None
    method: Optional[str] = None


def _card_text_and_links(card) -> tuple[str, list[str]]:
    text = card.get_text(" ", strip=True)
    hrefs = [a.get("href", "") for a in card.find_all("a", href=True)]
    return text, hrefs


def _extract_from_page(html: str, page_url: str, principal_name: str) -> Optional[PersonContactFacts]:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    own_domain = _site_domain(page_url)
    pattern = _name_pattern(principal_name)
    if not pattern:
        return None

    # Prefer the smallest/deepest card that contains the name (avoids matching a
    # whole page as "one card" when the name and an unrelated colleague's contact
    # both happen to appear in a large wrapping <div>).
    candidates = []
    for tagname in _CARD_TAGS:
        for card in soup.find_all(tagname):
            text, hrefs = _card_text_and_links(card)
            if len(text) > 600:          # too big to be a single person's card
                continue
            m = pattern.search(text)
            if not m:
                continue
            candidates.append((len(text), m.group(0), card, text, hrefs))
    candidates.sort(key=lambda t: t[0])  # smallest (most specific) card first

    for _, matched_name, card, text, hrefs in candidates:
        li = None
        for href in hrefs:
            m = _LINKEDIN_PERSON_RE.search(href)
            if m:
                slug = m.group(1).rstrip("/").split("?")[0]
                if slug:
                    li = f"https://www.linkedin.com/in/{slug}"
                    break
        email = None
        for raw in _EMAIL_RE.findall(text):
            e = raw.strip().strip(".")
            local, _, dom = e.partition("@")
            if _BAD_MAIL.search(local) or _BAD_MAIL.search(dom):
                continue
            if own_domain and dom.lower() != own_domain and not dom.lower().endswith("." + own_domain):
                continue  # only the firm's own domain counts as a corporate address
            email = e
            break
        if li or email:
            return PersonContactFacts(
                found=True, matched_name=matched_name, email=email, linkedin=li,
                source_url=page_url,
                method=f"firm team/about page, name-matched card ({'email' if email else ''}"
                       f"{'+' if email and li else ''}{'linkedin' if li else ''})")
    return None


class PersonContactEnricher:
    """Bounded fetch of a firm's team/about pages, name-matched to the principal.

    Reuses the same browser-ish, short-timeout, no-retry HTTP profile as
    WebsiteEnricher.web (a slow/dead team page must never stall the pipeline).
    """

    def __init__(self, http: Optional[HttpClient] = None):
        self.web = http or HttpClient(
            user_agent="Mozilla/5.0 (compatible; PolarityFOIntel/0.1)",
            accept="text/html,application/xhtml+xml", timeout=8, max_attempts=1)

    def find(self, website_url: str, principal_name: str,
             extra_pages: Optional[list[tuple[str, str]]] = None
             ) -> tuple[PersonContactFacts, list[EvidenceRef]]:
        """extra_pages: [(url, html)] already-fetched pages (e.g. homepage/about from
        WebsiteEnricher) to check before spending new HTTP calls on /team paths."""
        refs: list[EvidenceRef] = []
        if not website_url or not principal_name:
            return PersonContactFacts(found=False), refs

        for url, html in (extra_pages or []):
            facts = _extract_from_page(html, url, principal_name)
            if facts:
                return facts, refs

        base = website_url.rstrip("/")
        for path in _TEAM_PATHS:
            url = f"{base}/{path}"
            try:
                resp, ref = self.web.get_with_evidence(url, ext="html")
            except Exception as exc:
                log.warning("person-contact fetch failed", extra={
                    "event": "enrich_warn", "source": "person_contact", "url": url,
                    "error": str(exc)})
                continue
            if ref:
                refs.append(ref)
            facts = _extract_from_page(resp.text, resp.url, principal_name)
            if facts:
                return facts, refs
        return PersonContactFacts(found=False), refs
