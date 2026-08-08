"""
Discovery source — Web search via Tavily (keyed, robust replacement for the
rate-limited DuckDuckGo HTML endpoint used by enrichment/search.WebSearch).

Genuine discovery only: results whose titles/snippets name an explicit
"<Proper Name> Family Office" are surfaced as candidates; generic matches are
skipped so the pool never fills with noise. Requires TAVILY_API_KEY in the
environment; when it is absent the source yields nothing (and is skipped by
default_sources) so the rest of discovery is unaffected.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Iterator

from ..http import HttpClient
from ..observability import get_logger
from ..schema import Candidate, SourceClass
from ..text import norm_name
from .base import DiscoverySource

log = get_logger("discovery")

_FO_NAME = re.compile(
    r"\b([A-Z][A-Za-z.&\-' ]{2,45}?)\s+[Ff]amily\s+[Oo]ffice\b"
)
_STOPWORDS = {"the", "a", "an", "single", "multi", "your", "our", "his", "her", "their",
              "this", "that", "one", "new", "top", "best", "largest", "modern", "private",
              "how", "why", "what", "when", "inside", "meet", "is", "as", "of", "and"}


def _extract_fo_names(title: str) -> set[str]:
    names: set[str] = set()
    for m in _FO_NAME.finditer(title or ""):
        tokens = [t for t in m.group(1).strip().split("  ") if t]
        head = m.group(1).strip()
        head = re.sub(r"^['\"(]+|['\"):.,;]+$", "", head)
        tokens = head.split()
        while tokens and tokens[0].lower() in _STOPWORDS:
            tokens.pop(0)
        joined = " ".join(tokens)
        if len(joined) < 3:
            continue
        names.add(f"{joined} Family Office")
    return names


class TavilySearchSource(DiscoverySource):
    source_class = SourceClass.WEB
    SEARCH_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str | None = None, queries: list[str] | None = None):
        self.api_key = api_key
        self.http = HttpClient(accept="application/json", timeout=30, max_attempts=2)
        self.queries = queries or [
            '"family office" site:linkedin.com/company',
            '"{Name} Family Office" investment',
            "family office investments firm wealth",
        ]

    # -- Tavily endpoint ------------------------------------------------ #
    def _search(self, query: str, limit: int = 8) -> list[dict]:
        payload = {"query": query, "max_results": limit, "search_depth": "basic",
                   "api_key": self.api_key}
        resp = self.http.session.post(
            self.SEARCH_URL, json=payload,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=self.http.timeout)
        resp.raise_for_status()
        return (resp.json().get("results") or [])

    def discover(self, limit: int) -> Iterator[Candidate]:
        if not self.api_key:
            log.info("tavily skipped", extra={"event": "discover_skipped",
                                              "source": "tavily_search", "reason": "no api key"})
            return
        seen: set[str] = set()
        yielded = 0
        for query in self.queries:
            if yielded >= limit:
                break
            try:
                results = self._search(query)
            except Exception as exc:  # one query failing must not abort the source
                log.warning("tavily query failed", extra={"event": "search_error",
                                                          "query": query, "error": str(exc)})
                continue
            for r in results:
                title = r.get("title", "") or ""
                content = r.get("content", "") or ""
                for name in _extract_fo_names(f"{title} {content}"):
                    key = norm_name(name)
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    yield Candidate(
                        name=name,
                        source_class=self.source_class,
                        source_url=r.get("url"),
                        discovered_at=date.today(),
                        dedup_key=key,
                        raw={"title": title, "query": query},
                        hints={"from_headline": title},
                    )
                    yielded += 1
                    if yielded >= limit:
                        break
        log.info("tavily_search done", extra={"event": "discover_done",
                                              "source": "tavily_search", "count": yielded})


# Skips itself when unconfigured — safe to include directly in default_sources().
def get_tavily_source() -> DiscoverySource:
    from ..config import settings
    return TavilySearchSource(api_key=settings.tavily_api_key or None)