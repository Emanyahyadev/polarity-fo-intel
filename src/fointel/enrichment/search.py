"""
Web search (DuckDuckGo HTML endpoint) — used to FIND authoritative sources, never
as an authority itself. From results we extract a firm's official website and its
corporate LinkedIn; verification then happens against those authoritative pages.

Free, no API key. DuckDuckGo rate-limits, so this client throttles to 4s and the
results are cached per query.
"""

from __future__ import annotations

import re
import urllib.parse
from typing import Optional

from bs4 import BeautifulSoup

from ..http import HttpClient
from ..observability import get_logger

log = get_logger("enrichment")

# Aggregators / social / data-brokers — useful signals, but NOT a firm's own site.
_NON_OFFICIAL = re.compile(
    r"(linkedin|facebook|twitter|x\.com|instagram|crunchbase|bloomberg|wsj|forbes|reuters|"
    r"sec\.gov|whalewisdom|bizapedia|altss|unbiased|theadvisoros|adviserinfo|finnotes|"
    r"wikipedia|wikidata|fool\.com|intercreditreport|dnb\.com|zoominfo|pitchbook|"
    r"opencorporates|marketscreener|sec-api)", re.IGNORECASE)

_TOKEN = re.compile(r"[a-z0-9]+")


class SearchHit:
    __slots__ = ("title", "url")

    def __init__(self, title: str, url: str):
        self.title = title
        self.url = url


class WebSearch:
    HTML = "https://html.duckduckgo.com/html/"

    def __init__(self):
        self.http = HttpClient(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            pause=4.0, accept="text/html")
        self._cache: dict[str, list[SearchHit]] = {}

    def search(self, query: str, limit: int = 8) -> list[SearchHit]:
        if query in self._cache:
            return self._cache[query]
        try:
            resp = self.http.get(self.HTML, params={"q": query})
        except Exception as exc:
            log.warning("search failed", extra={"event": "search_error", "query": query,
                                                "error": str(exc)})
            self._cache[query] = []
            return []
        soup = BeautifulSoup(resp.text, "lxml")
        hits: list[SearchHit] = []
        for a in soup.select("a.result__a")[:limit]:
            href = a.get("href", "")
            m = re.search(r"uddg=([^&]+)", href)
            url = urllib.parse.unquote(m.group(1)) if m else href
            if url.startswith("http"):
                hits.append(SearchHit(a.get_text(strip=True), url))
        self._cache[query] = hits
        return hits

    # -- extraction from results --------------------------------------- #
    @staticmethod
    def official_website(firm_name: str, hits: list[SearchHit]) -> Optional[str]:
        """First result on a domain that looks like the firm's own (not an aggregator)."""
        name_tokens = {t for t in _TOKEN.findall(firm_name.lower())
                       if len(t) > 2 and t not in {"llc", "lp", "inc", "the", "family", "office",
                                                   "capital", "group", "management", "partners"}}
        for hit in hits:
            host = urllib.parse.urlparse(hit.url).netloc.lower()
            if _NON_OFFICIAL.search(host):
                continue
            domain = host.split(":")[0].replace("www.", "")
            domain_tokens = set(_TOKEN.findall(domain.split(".")[0]))
            if name_tokens & domain_tokens:      # a firm-name token appears in the domain
                return f"https://{host}".rstrip("/")
        return None

    @staticmethod
    def linkedin_company(hits: list[SearchHit]) -> Optional[str]:
        for hit in hits:
            if re.search(r"linkedin\.com/company/", hit.url, re.IGNORECASE):
                return hit.url.split("?")[0]
        return None
