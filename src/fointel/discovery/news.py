"""
Discovery source 3 — News / press via GDELT (media lens).

GDELT is used (not Google News RSS) for a specific reason documented in the
methodology: Google News RSS's terms restrict it to personal, non-commercial feed
rendering, which a commercial dataset pipeline would violate. GDELT's DOC API is
open for programmatic research.

Empirical finding (documented in the methodology): the generic "family office"
query is a WEAK discovery channel — GDELT's coverage of this niche B2B term is thin
and noisy. So this lens is repositioned: best-effort discovery here, but its real
value is per-firm SIGNALS in the enrichment layer (querying a specific firm name
returns relevant recent coverage). GDELT rate-limits to ~1 request/5s -> 6s throttle.
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

log = get_logger("pipeline")

# "Walton Enterprises", "Bezos Expeditions" won't match; this catches explicit
# "<Proper Name> Family Office" mentions, which are unambiguous FO references.
_FO_NAME = re.compile(
    r"\b([A-Z][A-Za-z.&'\-]+(?:\s+[A-Z][A-Za-z.&'\-]+){0,3})\s+[Ff]amily\s+[Oo]ffice\b"
)
_STOPWORDS = {"the", "a", "an", "single", "multi", "your", "our", "his", "her", "their",
              "this", "that", "one", "new", "top", "best", "largest", "modern", "private",
              "how", "why", "what", "when", "inside", "meet", "is", "as", "of", "and"}


def _extract_fo_names(text: str) -> set[str]:
    names: set[str] = set()
    for m in _FO_NAME.finditer(text or ""):
        tokens = m.group(1).strip().split()
        while tokens and tokens[0].lower() in _STOPWORDS:  # drop a leading "The"/"A"/...
            tokens.pop(0)
        head = " ".join(tokens)
        if len(head) < 3:  # nothing distinctive left -> generic "family office"
            continue
        names.add(f"{head} Family Office")
    return names


class NewsSource(DiscoverySource):
    source_class = SourceClass.NEWS
    DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self, query: str = '"family office" sourcelang:english',
                 timespan: str = "6months", maxrecords: int = 100):
        self.http = HttpClient(pause=6.0, accept="application/json")  # GDELT: >=5s between calls
        self.query = query
        self.timespan = timespan
        self.maxrecords = maxrecords

    def discover(self, limit: int) -> Iterator[Candidate]:
        data = self.http.get_json(self.DOC_URL, params={
            "query": self.query, "mode": "artlist", "format": "json",
            "maxrecords": self.maxrecords, "sort": "datedesc", "timespan": self.timespan,
        })
        articles = data.get("articles", []) if isinstance(data, dict) else []
        seen: set[str] = set()
        yielded = 0
        for art in articles:
            title = art.get("title", "")
            for name in _extract_fo_names(title):
                key = norm_name(name)
                if not key or key in seen:
                    continue
                seen.add(key)
                yield Candidate(
                    name=name,
                    source_class=self.source_class,
                    source_url=art.get("url"),
                    discovered_at=date.today(),
                    dedup_key=key,
                    raw={"article_title": title, "domain": art.get("domain"),
                         "seendate": art.get("seendate"), "language": art.get("language")},
                    hints={"from_headline": title},
                )
                yielded += 1
                if yielded >= limit:
                    log.info("news done", extra={"event": "discover_done", "source": "news",
                                                 "count": yielded})
                    return
        log.info("news done", extra={"event": "discover_done", "source": "news", "count": yielded})
