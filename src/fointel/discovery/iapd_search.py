"""
Discovery source 5 — SEC IAPD / Form ADV registry search.

IAPD (IARD) is the investment-adviser registration system — a different filing
system from EDGAR 13F. Searching it for "family office" surfaces the ~hundreds of
registered US family offices, most of which do NOT file 13F and are therefore
invisible to the EDGAR lens. Each hit carries the firm's registered name/aliases
(family-office confirmation) and office address.

Only firms whose registered name/aliases actually contain "family office" are
yielded (the query can match loosely), so this is genuine family-office discovery.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Iterator

from ..http import HttpClient
from ..observability import get_logger
from ..schema import Candidate, SourceClass
from ..text import norm_name
from .base import DiscoverySource

log = get_logger("discovery")

_FO = re.compile(r"family office", re.IGNORECASE)


class IapdSearchSource(DiscoverySource):
    source_class = SourceClass.SEC_IAPD
    SEARCH = "https://api.adviserinfo.sec.gov/search/firm"

    def __init__(self, query: str = "family office", page_size: int = 100):
        self.http = HttpClient(user_agent="Mozilla/5.0", accept="application/json",
                               timeout=25, max_attempts=2)
        self.query = query
        self.page_size = page_size

    def discover(self, limit: int) -> Iterator[Candidate]:
        seen: set[str] = set()
        yielded = skipped = 0
        start = 0
        while yielded < limit:
            data = self.http.get_json(self.SEARCH, params={
                "query": self.query, "hits": self.page_size, "start": start,
                "includeInactive": "false"})
            hits = ((data.get("hits") or {}).get("hits")) or []
            if not hits:
                break
            for hit in hits:
                src = hit.get("_source", {})
                names = [src.get("firm_name", "")] + (src.get("firm_other_names") or [])
                if not _FO.search(" ".join(names)):        # registry match must be a real FO name
                    skipped += 1
                    continue
                crd = str(src.get("firm_source_id") or "")
                if not crd or crd in seen:
                    continue
                seen.add(crd)
                name = src.get("firm_name", "").strip()
                try:
                    addr = (json.loads(src.get("firm_ia_address_details") or "{}")
                            ).get("officeAddress", {}) or {}
                except (json.JSONDecodeError, TypeError):
                    addr = {}
                yield Candidate(
                    name=name, source_class=self.source_class,
                    source_url=f"https://adviserinfo.sec.gov/firm/summary/{crd}",
                    discovered_at=date.today(), dedup_key=norm_name(name),
                    identifiers={"crd": crd},
                    raw={"crd": crd, "sec_number": src.get("firm_ia_full_sec_number"),
                         "other_names": [n for n in names if n]},
                    hints={"city": addr.get("city"), "state": addr.get("state"),
                           "country": addr.get("country")})
                yielded += 1
                if yielded >= limit:
                    break
            start += len(hits)
        log.info("iapd_search done", extra={"event": "discover_done", "source": "iapd_search",
                                            "count": yielded, "skipped": skipped})
