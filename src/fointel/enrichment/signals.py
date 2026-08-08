"""
Signals enrichment — recent, dated activity per firm (commercial-value driver).

GDELT's per-firm query (the exact firm name) is far more relevant than the generic
"family office" query. Each qualifying article becomes a dated Signal cited to its
source. Coverage is genuinely sparse for private family offices — most have no
press — so many records honestly carry no signals rather than filler.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from ..http import HttpClient
from ..observability import get_logger
from ..schema import Confidence, Signal, SourceClass

log = get_logger("enrichment")


def _parse_gdelt_date(seendate: Optional[str]) -> Optional[date]:
    if not seendate or len(seendate) < 8:
        return None
    try:
        return date(int(seendate[0:4]), int(seendate[4:6]), int(seendate[6:8]))
    except (ValueError, TypeError):
        return None


class SignalsEnricher:
    DOC = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(self):
        # GDELT rate-limits aggressively. We retry with exponential backoff up to 4 times
        # to ensure we don't miss signals due to temporary rate limits. >=6s base pacing.
        self.http = HttpClient(pause=6.0, accept="application/json", timeout=15, max_attempts=4)

    def firm_signals(self, firm_name: str, max_signals: int = 3,
                     timespan: str = "12months") -> list[Signal]:
        try:
            data = self.http.get_json(self.DOC, params={
                "query": f'"{firm_name}"', "mode": "artlist", "format": "json",
                "maxrecords": 20, "sort": "datedesc", "timespan": timespan})
        except Exception as exc:
            log.debug("signals fetch failed", extra={"event": "enrich_warn", "source": "signals",
                        "firm": firm_name, "error": str(exc)})
            return []
        articles = data.get("articles", []) if isinstance(data, dict) else []
        anchor = firm_name.split()[0].lower()
        signals: list[Signal] = []
        seen_titles: set[str] = set()
        for art in articles:
            title = (art.get("title") or "").strip()
            if not title or anchor not in title.lower():   # keep only firm-relevant coverage
                continue
            if not art.get("url"):    # a dated signal must be traceable to a source URL, else drop it
                continue
            key = title.lower()[:80]
            if key in seen_titles:
                continue
            seen_titles.add(key)
            signals.append(Signal(
                text=title, source_class=SourceClass.NEWS,
                event_date=_parse_gdelt_date(art.get("seendate")),
                source_url=art.get("url"), confidence=Confidence.MEDIUM))
            if len(signals) >= max_signals:
                break
        return signals
