"""
Domain discovery via the keyed search providers — the working replacement for
`enrichment.search.WebSearch`, which scrapes DuckDuckGo's unkeyed HTML endpoint
and was measured returning 0 hits for every query during this session's
audit (docs/evidence/domain-search-provider-audit.json).

This module answers one narrow question: "what is this firm's official
website?" — not general web search. It reuses the same three keyed providers
already paying for themselves in discovery (Tavily, Exa, Serper; see
discovery/tavily_search.py, exa_search.py, serper_search.py), tried in that
order, first provider to return a usable, non-registry URL wins. It returns
provenance (provider, query, raw URL) so a caller can record exactly which
provider supplied the candidate domain — verification that the domain
actually belongs to the firm happens in the caller (website.py's
_page_belongs_to identity guard), not here. This module never asserts a
domain is correct; it only proposes one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import requests

from ..config import settings
from ..observability import get_logger

log = get_logger("enrichment")

# Reference/registry/social hosts a search hit commonly returns that are never
# the firm's OWN site — surfacing one of these as "the domain" would attach a
# third party's page as if it were the firm's evidence.
_NOT_OFFICIAL = re.compile(
    r"(sec\.gov|wikipedia\.org|wikidata\.org|propublica\.org|linkedin\.com|"
    r"bloomberg\.com|crunchbase\.com|zoominfo\.com|facebook\.com|twitter\.com|"
    r"x\.com|instagram\.com|youtube\.com|glassdoor\.com|indeed\.com|"
    r"sec\.report|opencorporates\.com|dnb\.com|adviserinfo\.sec\.gov|"
    r"bing\.com|google\.com|duckduckgo\.com)", re.I)


@dataclass
class DomainHit:
    url: str
    provider: str
    query: str


_STOPWORDS = {"the", "and", "llc", "lp", "llp", "inc", "incorporated", "ltd",
             "limited", "company", "co", "group", "capital", "partners",
             "management", "advisors", "advisers", "family", "office",
             "offices", "trust", "holdings", "investment", "investments"}


def _identity_tokens(firm_name: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", (firm_name or "").lower())
    return [w for w in words if w not in _STOPWORDS and len(w) > 2]


def _first_official(results: list[dict], url_key: str, firm_name: str) -> Optional[str]:
    """A URL is only a domain candidate if BOTH it isn't a known non-firm host
    (registry/social/reference) AND its own domain contains a distinctive token
    of the firm's name. Media coverage of a firm (a Forbes profile, a press-wire
    story) passes the first check but not the second — press mentions the firm,
    it is not the firm's site, and treating it as one would misattribute
    third-party text as the firm's own evidence. Measured need: Tavily's top hit
    for "Pathstone Holdings, LLC" was forbes.com/companies/pathstone — real
    content, wrong owner."""
    tokens = _identity_tokens(firm_name)
    for r in results:
        url = (r.get(url_key) or "").strip()
        if not url or not url.lower().startswith("http"):
            continue
        if _NOT_OFFICIAL.search(url):
            continue
        m = re.search(r"https?://(?:www\.)?([^/?#]+)", url.lower())
        host = m.group(1) if m else ""
        host_norm = re.sub(r"[^a-z0-9]", "", host)
        if tokens and not any(t in host_norm for t in tokens):
            continue
        return url
    return None


def _tavily(query: str, firm_name: str) -> Optional[str]:
    if not settings.tavily_api_key:
        return None
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={"query": query, "max_results": 5, "search_depth": "basic",
                 "api_key": settings.tavily_api_key},
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"}, timeout=15)
        resp.raise_for_status()
        return _first_official(resp.json().get("results") or [], "url", firm_name)
    except Exception as exc:
        log.warning("tavily domain search failed", extra={
            "event": "enrich_warn", "source": "domain_search", "provider": "tavily",
            "error": str(exc)[:160]})
        return None


def _exa(query: str, firm_name: str) -> Optional[str]:
    if not settings.exa_api_key:
        return None
    try:
        resp = requests.post(
            "https://api.exa.ai/search",
            json={"query": query, "numResults": 5, "type": "auto"},
            headers={"x-api-key": settings.exa_api_key, "Content-Type": "application/json"},
            timeout=15)
        resp.raise_for_status()
        return _first_official(resp.json().get("results") or [], "url", firm_name)
    except Exception as exc:
        log.warning("exa domain search failed", extra={
            "event": "enrich_warn", "source": "domain_search", "provider": "exa",
            "error": str(exc)[:160]})
        return None


def _serper(query: str, firm_name: str) -> Optional[str]:
    if not settings.serper_api_key:
        return None
    try:
        resp = requests.post(
            "https://google.serper.dev/search",
            json={"q": query, "num": 5},
            headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
            timeout=15)
        resp.raise_for_status()
        return _first_official(resp.json().get("organic") or [], "link", firm_name)
    except Exception as exc:
        log.warning("serper domain search failed", extra={
            "event": "enrich_warn", "source": "domain_search", "provider": "serper",
            "error": str(exc)[:160]})
        return None


_PROVIDERS = (("tavily", _tavily), ("exa", _exa), ("serper", _serper))


def find_official_domain(firm_name: str) -> Optional[DomainHit]:
    """Try each keyed provider in turn; first usable, non-registry URL wins.
    Returns None (never a guess) if no provider yields anything or no keys
    are configured. Caller MUST still verify the returned page actually
    belongs to the firm before treating it as evidence."""
    query = f'"{firm_name}" official website'
    for name, fn in _PROVIDERS:
        url = fn(query, firm_name)
        if url:
            log.info("domain search hit", extra={
                "event": "enrich_info", "source": "domain_search",
                "provider": name, "firm": firm_name, "url": url})
            return DomainHit(url=url, provider=name, query=query)
    return None
