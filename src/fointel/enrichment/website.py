"""
Website enrichment — the authoritative corroboration a firm's own site provides.

For directory-discovered firms (Wikipedia/Wikidata are discovery-only and cannot
verify, per the release gate), the firm's **official website** is the authoritative
source that confirms family-office status, resolves SFO/MFO, and supplies a
description and AUM. Official URLs come from Wikidata P856; Wikipedia's intro text
is used only as cited *background* (never as FO-verification).

Every fetch is snapshotted (content hash) for reproducible provenance.
"""

from __future__ import annotations

import re
from typing import Optional

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from ..evidence import EvidenceRef
from ..http import HttpClient
from ..observability import get_logger

log = get_logger("enrichment")

_FO = re.compile(r"family office", re.IGNORECASE)
_SFO = re.compile(r"single[- ]?family office", re.IGNORECASE)
_MFO = re.compile(r"multi[- ]?family office", re.IGNORECASE)
# investment-thesis / mandate language a firm states about ITS OWN approach
_THESIS_KW = re.compile(
    r"\b(invest\w*|approach|philosoph\w*|strateg\w*|mission|believe|focus\w*|"
    r"generation\w*|preserv\w*|steward\w*|mandate|long[- ]term|values|legacy|"
    r"grow\w*|protect\w*|capital|portfolio|wealth)\b", re.I)
_NAV_KW = re.compile(
    r"\b(cookie|privacy|copyright|all rights|©|menu|navigation|subscribe|newsletter|"
    r"terms of|log ?in|sign ?in|404|not found|javascript|enable)\b", re.I)


def _looks_like_prose(s: str) -> bool:
    """True for a real sentence, False for a concatenated navigation menu. Menus are
    mostly Capitalized nouns with no connective words; prose has lowercase function words."""
    words = s.split()
    if len(words) < 7:
        return False
    if sum(1 for w in words if w[:1].isupper()) / len(words) > 0.5:
        return False
    return bool(re.search(r"\b(we|our|is|are|to|of|and|for|with|that|your|help\w*|"
                          r"believe|partner\w*|manage\w*|provide\w*|approach|serve\w*)\b", s))


def extract_thesis(text: str) -> Optional[str]:
    """Pick the sentence that best states the firm's own investment approach/mission —
    an attributable quote from its site, not a synthesis. Requires >=2 thesis cues, real
    prose (not a nav menu), and no boilerplate. None if the site has no such statement."""
    best, best_score = None, 0
    for raw in re.split(r"(?<=[.!?])\s+", text):
        s = raw.strip()
        if not (45 <= len(s) <= 280) or _NAV_KW.search(s) or not _looks_like_prose(s):
            continue
        score = len(set(m.lower()[:6] for m in _THESIS_KW.findall(s)))
        if _FO.search(s):
            score += 1
        if score > best_score:
            best, best_score = s, score
    return best if best_score >= 2 else None
_AUM = re.compile(
    r"(?:aum|assets under management|manages?|oversees?)[^.$]{0,40}"
    r"(\$[\d.,]+\s*(?:billion|million|bn|mn|b|m)\b)", re.IGNORECASE)
_AUM2 = re.compile(r"(\$[\d.,]+\s*(?:billion|million|bn|mn)\b)[^.]{0,30}"
                   r"(?:assets|aum|under management)", re.IGNORECASE)

# Contact intelligence the SITE itself publishes (mailto links + its LinkedIn page).
# Only the firm's OWN published outreach channels count; foreign-domain mailboxes
# (hosting/marketing vendors) and boilerplate addresses are ignored.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,24}")
_ROLE_INBOX = re.compile(r"^(info|contact|office|hello|admin|mail|invest|connect|enquir|"
                         r"family[- ]?office|reception|manage|team)@", re.I)
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/"
                          r"(?:company|pages/company|showcase)/([A-Za-z0-9_\-]+)")
_LINKEDIN_JUNK = {"jobs", "life", "about", "careers", "people", "topics", "posts", "feed"}
_BAD_TLDS = {"png", "jpg", "jpeg", "gif", "svg", "webp", "css", "js"}
_BAD_MAIL = re.compile(r"(noreply|no-?reply|donotreply|example|test|pixel|tracking|"
                       r"wixpress|sentry|campaign|newsletter@)", re.I)


def _site_domain(url: Optional[str]) -> str:
    """Own registrable host of the fetched page (www-stripped), '' if unknown."""
    m = re.search(r"https?://(?:www\.)?([^/?#]+)", (url or "").strip().lower())
    return (m.group(1) or "") if m else ""


def extract_contacts(text: str, url: Optional[str] = None) -> tuple[list[str], Optional[str]]:
    """(emails, linkedin_company_url) that the firm's own site publishes.

    Emails: only mailboxes on the site's OWN domain (or one of its subdomains),
    junk local parts (noreply/example/pixel/vendor) filtered, the site's role
    inbox (info@ / contact@ / office@ ...) preferred. Never a guess: everything
    here was on the firm's official pages. Foreign-domain addresses (hosting or
    marketing vendors) are dropped — they are not the firm's outreach channel.
    """
    own = _site_domain(url)
    emails, seen = [], set()
    for raw in re.findall(_EMAIL_RE, text or ""):
        e = raw.strip().strip(".")
        name, _, dom = e.partition("@")
        tld = dom.rsplit(".", 1)[-1].lower()
        if len(e) < 7 or len(dom) < 5 or tld in _BAD_TLDS:
            continue
        if _BAD_MAIL.search(name) or _BAD_MAIL.search(dom):
            continue
        if own and dom != own and not dom.endswith("." + own):
            continue
        key = e.lower()
        if key in seen:
            continue
        seen.add(key)
        emails.append(e)
    emails.sort(key=lambda e: (_ROLE_INBOX.search(e) is None, "." in e.split("@")[1]))
    if not own and not emails:
        emails = []
    li = None
    for slug in _LINKEDIN_RE.findall(text or ""):
        s = slug.rstrip("/").split("?")[0]
        if not s or s.lower() in _LINKEDIN_JUNK:
            continue
        li = f"https://www.linkedin.com/company/{s}"
        break
    return emails, li


class WebsiteFacts(BaseModel):
    url: Optional[str] = None
    resolved: bool = False
    fo_language: bool = False           # site describes itself as a family office
    fo_type_hint: Optional[str] = None  # "SFO" / "MFO" / None
    description: Optional[str] = None
    aum_text: Optional[str] = None
    thesis: Optional[str] = None
    emails: list[str] = Field(default_factory=list)   # contact mailboxes published on the site
    linkedin: Optional[str] = None                    # LinkedIn company page the site links
    text_excerpt: str = ""


def analyze_text(text: str) -> tuple[bool, Optional[str], Optional[str]]:
    """Pure text analysis: (family-office language, SFO/MFO hint, AUM text). Testable, no I/O."""
    type_hint = "SFO" if _SFO.search(text) else ("MFO" if _MFO.search(text) else None)
    aum = None
    for pat in (_AUM, _AUM2):
        m = pat.search(text)
        if m:
            aum = m.group(1)
            break
    return bool(_FO.search(text)), type_hint, aum


class WebsiteEnricher:
    WD_ENTITY = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
    WIKI_API = "https://en.wikipedia.org/w/api.php"

    def __init__(self):
        self.http = HttpClient()
        # a browser-ish UA for firm sites (many reject unknown agents); short timeout
        # and no retry so a slow/dead site cannot stall the pipeline.
        self.web = HttpClient(user_agent="Mozilla/5.0 (compatible; PolarityFOIntel/0.1)",
                              accept="text/html,application/xhtml+xml", timeout=8, max_attempts=1)

    # -- URL discovery ------------------------------------------------- #
    def wikipedia_title_to_qid(self, title: str) -> Optional[str]:
        data = self.http.get_json(self.WIKI_API, params={
            "action": "query", "prop": "pageprops", "ppprop": "wikibase_item",
            "titles": title, "format": "json"})
        for page in (data.get("query", {}).get("pages", {}) or {}).values():
            qid = (page.get("pageprops") or {}).get("wikibase_item")
            if qid:
                return qid
        return None

    def wikidata_official_site(self, qid: str) -> Optional[str]:
        data = self.http.get_json(self.WD_ENTITY.format(qid=qid))
        claims = (data.get("entities", {}).get(qid, {}) or {}).get("claims", {})
        p856 = claims.get("P856")
        if p856:
            try:
                return p856[0]["mainsnak"]["datavalue"]["value"]
            except (KeyError, IndexError, TypeError):
                return None
        return None

    def wikipedia_intro(self, title: str) -> Optional[str]:
        data = self.http.get_json(self.WIKI_API, params={
            "action": "query", "prop": "extracts", "exintro": "1", "explaintext": "1",
            "titles": title, "format": "json"})
        for page in (data.get("query", {}).get("pages", {}) or {}).values():
            extract = page.get("extract")
            if extract:
                return extract.strip()
        return None

    # -- site fetch ---------------------------------------------------- #
    def fetch_site(self, url: str) -> tuple[WebsiteFacts, Optional[EvidenceRef]]:
        try:
            resp, ref = self.web.get_with_evidence(url, ext="html")
        except Exception as exc:
            log.warning("site fetch failed", extra={"event": "enrich_warn",
                        "source": "website", "url": url, "error": str(exc)})
            return WebsiteFacts(url=url, resolved=False), None

        soup = BeautifulSoup(resp.text, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()

        desc = None
        meta = (soup.find("meta", attrs={"name": "description"})
                or soup.find("meta", attrs={"property": "og:description"}))
        if meta and meta.get("content"):
            desc = meta["content"].strip()[:400]

        fo_language, type_hint, aum = analyze_text(text)
        mail_hrefs = [h[7:].split("?")[0] for h in
                      (a.get("href", "") for a in soup.find_all("a", href=True))
                      if h.lower().startswith("mailto:")]
        emails, linkedin = extract_contacts("\n".join(mail_hrefs) + "\n" + text, resp.url)
        return WebsiteFacts(
            url=resp.url, resolved=True, fo_language=fo_language,
            fo_type_hint=type_hint, description=desc, aum_text=aum,
            thesis=extract_thesis(text), emails=emails, linkedin=linkedin,
            text_excerpt=text[:1500]), ref

    _ABOUT_PATHS = ("about", "about-us")
    _CONTACT_PATHS = ("contact", "contact-us")

    @staticmethod
    def _absorb(dst: "WebsiteFacts", src: "WebsiteFacts") -> bool:
        """Copy contact data from src into dst if dst lacks it. True if dst changed."""
        changed = False
        if not dst.emails and src.emails:
            dst.emails = list(src.emails)
            changed = True
        if not dst.linkedin and src.linkedin:
            dst.linkedin = src.linkedin
            changed = True
        return changed

    # Words that carry no identity on their own — a page matching only these has
    # not been shown to belong to the candidate.
    _STOPWORDS = {"the", "and", "llc", "lp", "llp", "inc", "incorporated", "ltd",
                  "limited", "company", "co", "group", "capital", "partners",
                  "management", "advisors", "advisers", "family", "office",
                  "offices", "trust", "holdings", "investment", "investments"}

    @classmethod
    def _identity_tokens(cls, firm_name: str) -> list[str]:
        """Distinctive tokens of a firm name — what must appear on a page before we
        accept that page as belonging to THIS firm."""
        words = re.findall(r"[a-z0-9]+", (firm_name or "").lower())
        return [w for w in words if w not in cls._STOPWORDS and len(w) > 2]

    @classmethod
    def _page_belongs_to(cls, html: str, firm_name: str) -> bool:
        """Identity guard: a resolved domain is only usable as evidence if the page
        actually names the candidate. Prevents attaching 'smithfamilyoffice.com' to a
        different Smith family office (a constructed domain is a guess until proven)."""
        toks = cls._identity_tokens(firm_name)
        if not toks:
            return False
        text = (html or "").lower()
        return sum(1 for t in toks if t in text) >= max(1, min(2, len(toks)))

    def _accept(self, url: str, firm_name: str) -> Optional[str]:
        """Fetch `url` and accept it only if the page BOTH names the firm and carries
        family-office language. Returns the confirmed URL or None."""
        try:
            resp = self.web.get(url)
        except Exception:
            return None
        if not self._page_belongs_to(resp.text, firm_name):
            return None
        if not _FO.search(resp.text):
            return None
        return str(resp.url).rstrip("/") or url.rstrip("/")

    def resolve_domain(self, firm_name: str,
                       source_url: Optional[str] = None) -> Optional[str]:
        """Bounded multi-strategy official-site resolution.

        Order: (1) the domain the discovery source already gave us, (2) constructed
        domains, (3) web-search official-site discovery. Every strategy ends at the
        same verification — the page must name the firm AND self-describe as a family
        office — so a domain is never trusted merely because it resolved. Returns None
        rather than a guess.

        Previously this was only ever CALLED for candidates whose name literally
        contained "family office" (assemble.py's `likely_fo` gate). A 30-candidate
        audit showed that gate blocked 18/30 (60%) from any evidence acquisition at
        all, so a genuine family office not named "...Family Office" could never
        qualify. The gate is gone; this resolver is the bounded replacement.
        """
        tried: list[str] = []

        # 1. the discovery source's own URL, when it points at the firm's own site
        if source_url:
            m = re.search(r"https?://[^/?#]+", source_url)
            host = m.group(0) if m else ""
            if host and not re.search(
                    r"(sec\.gov|wikipedia\.org|wikidata\.org|propublica\.org|"
                    r"linkedin\.com|bloomberg\.com|crunchbase\.com)", host, re.I):
                tried.append(host)
                got = self._accept(host, firm_name)
                if got:
                    return got

        # 2. constructed domains (cheap, no API budget)
        lower = re.sub(r"[^a-z0-9 ]", "", (firm_name or "").lower())
        head = re.sub(r"\bfamily office.*", "", lower).strip().replace(" ", "")
        nospace = lower.replace(" ", "")
        for domain in dict.fromkeys([nospace + ".com", head + "familyoffice.com",
                                     head + "fo.com", lower.replace(" ", "-") + ".com"]):
            if len(domain) < 9 or domain in tried:
                continue
            tried.append(domain)
            got = self._accept("https://" + domain, firm_name)
            if got:
                return got

        # 3. keyed-provider official-site discovery (Tavily -> Exa -> Serper) — the
        #    strategy that reaches firms whose domain is not derivable from their
        #    name. Previously used enrichment.search.WebSearch, which scrapes the
        #    unkeyed DuckDuckGo HTML endpoint and was measured returning 0 hits for
        #    every query in this session's provider audit (a 30-candidate before/
        #    after test showed literally zero change from removing the name gate,
        #    because this fallback was dead). domain_search.find_official_domain
        #    additionally requires the returned domain itself (not just the page
        #    text) to contain a distinctive token of the firm's name, so a media
        #    profile of the firm (e.g. forbes.com/companies/pathstone) cannot be
        #    mistaken for the firm's own site.
        try:
            from .domain_search import find_official_domain
            hit = find_official_domain(firm_name)
            if hit and hit.url not in tried:
                got = self._accept(hit.url, firm_name)
                if got:
                    log.info("domain resolved via keyed provider", extra={
                        "event": "enrich_info", "source": "website",
                        "firm": firm_name, "provider": hit.provider, "url": got})
                    return got
        except Exception as exc:  # provider search is best-effort; never sink enrichment
            log.warning("domain search failed", extra={
                "event": "enrich_warn", "source": "website",
                "firm": firm_name, "error": str(exc)[:160]})
        return None

    def fetch_site_deep(self, url: str) -> tuple[WebsiteFacts, list[EvidenceRef]]:
        """Homepage first; if it does not confirm family-office status, try common
        /about pages (the phrase often lives there, not on the homepage). Contact
        pages are fetched when the pages seen so far published no email/LinkedIn
        (the firm's contact channel usually lives there, not on the homepage)."""
        refs: list[EvidenceRef] = []
        facts, ref = self.fetch_site(url)
        if ref:
            refs.append(ref)
        base = url.rstrip("/")

        def try_contact(dst: WebsiteFacts) -> bool:
            if dst.emails or dst.linkedin:
                return True
            for path in self._CONTACT_PATHS:
                more, ref2 = self.fetch_site(f"{base}/{path}")
                if not more.resolved:
                    continue
                if ref2:
                    refs.append(ref2)
                self._absorb(dst, more)
                if dst.emails or dst.linkedin:
                    return True
            return bool(dst.emails or dst.linkedin)

        if facts.resolved and facts.fo_language:
            try_contact(facts)
            return facts, refs
        for path in self._ABOUT_PATHS:
            more, ref2 = self.fetch_site(f"{base}/{path}")
            if not more.resolved:
                continue
            if ref2:
                refs.append(ref2)
            if more.fo_language:                     # /about confirms FO -> merge and stop
                more.url = facts.url or url
                more.description = facts.description or more.description
                self._absorb(more, facts)            # keep homepage contacts as well
                return more, refs
        try_contact(facts)
        return facts, refs

