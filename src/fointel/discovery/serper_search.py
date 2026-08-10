"""
Discovery source — Web search via Serper.dev (keyed realtime Google SERP API).

Same contract as the Tavily/EXA sources: only results that name an explicit
"<Proper Name> Family Office" are surfaced, so discovery stays genuine. Requires
SERPER_API_KEY; without it the source yields nothing (and default_sources skips
it) so the rest of discovery is unaffected.
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


def _extract_fo_names(text: str) -> set[str]:
    names: set[str] = set()
    for m in _FO_NAME.finditer(text or ""):
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


class SerperSearchSource(DiscoverySource):
    source_class = SourceClass.SERP
    SEARCH_URL = "https://google.serper.dev/search"

    def __init__(self, api_key: str | None = None, queries: list[str] | None = None):
        self.api_key = api_key
        self.http = HttpClient(accept="application/json", timeout=30, max_attempts=2)
        self.queries = queries or [
            '"family office" investment firm',
            '"single family office" investor',
            '"multi family office"',
            '"family office" financial advisor firm',
            '"family office" new launch',
        ]

    def _search(self, query: str, limit: int = 8) -> list[dict]:
        payload = {"q": query, "num": limit}
        resp = self.http.session.post(
            self.SEARCH_URL, json=payload,
            headers={"X-API-KEY": self.api_key, "Content-Type": "application/json"},
            timeout=self.http.timeout)
        resp.raise_for_status()
        return (resp.json().get("organic") or [])

    def discover(self, limit: int) -> Iterator[Candidate]:
        if not self.api_key:
            log.info("serper skipped", extra={"event": "discover_skipped",
                                              "source": "serper", "reason": "no api key"})
            return
        seen: set[str] = set()
        yielded = 0
        for query in self.queries:
            if yielded >= limit:
                break
            try:
                results = self._search(query, limit=16)
            except Exception as exc:
                log.warning("serper query failed", extra={"event": "search_error",
                                                          "query": query, "error": str(exc)})
                continue
            for r in results:
                title = r.get("title", "") or ""
                snippet = r.get("snippet", "") or ""
                for name in _extract_fo_names(f"{title} {snippet}"):
                    key = norm_name(name)
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    yield Candidate(
                        name=name,
                        source_class=self.source_class,
                        source_url=r.get("link"),
                        discovered_at=date.today(),
                        dedup_key=key,
                        raw={"title": title, "query": query},
                        hints={"from_headline": title},
                    )
                    yielded += 1
                    if yielded >= limit:
                        break
        log.info("serper done", extra={"event": "discover_done",
                                       "source": "serper", "count": yielded})


def get_serper_source() -> DiscoverySource:
    from ..config import settings
    return SerperSearchSource(api_key=settings.serper_api_key or None)