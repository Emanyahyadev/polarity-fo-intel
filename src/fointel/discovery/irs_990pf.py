"""
Discovery source 2 — IRS 990-PF via ProPublica Nonprofit Explorer (tax-exempt lens).

Rationale (DecisionLog D2): many single-family offices sit beside a family private
foundation. Searching foundation/family-investment entities surfaces family leads
the regulatory and directory lenses miss, plus principals (trustees/officers) and
location from the 990-PF.

Honest limitation, documented in the methodology: most family offices are for-profit
and therefore under-represented in 990 data. This lens contributes *diversity* and
*SFO leads*, not bulk yield. Whether a discovered family actually runs a family
office is decided later by the validation layer — discovery never proves.
"""

from __future__ import annotations

from datetime import date
from typing import Iterator

from ..http import HttpClient
from ..observability import get_logger
from ..schema import Candidate, SourceClass
from ..text import norm_name
from .base import DiscoverySource

log = get_logger("discovery")


class Irs990pfSource(DiscoverySource):
    source_class = SourceClass.IRS_990PF
    SEARCH_URL = "https://projects.propublica.org/nonprofits/api/v2/search.json"

    def __init__(self, queries: tuple[str, ...] = (
        "family office", "family investment", "family capital", "family partners",
    )):
        self.http = HttpClient()
        self.queries = queries

    def discover(self, limit: int) -> Iterator[Candidate]:
        seen_eins: set[str] = set()
        yielded = 0
        skipped = 0
        for query in self.queries:
            page = 0
            while yielded < limit:
                data = self.http.get_json(self.SEARCH_URL, params={"q": query, "page": page})
                orgs = data.get("organizations", [])
                if not orgs:
                    break
                for org in orgs:
                    ein = str(org.get("ein") or "")
                    if not ein:
                        skipped += 1
                        log.debug("skip: org without EIN", extra={"event": "skip",
                                  "source": "irs_990pf", "reason": "no_ein"})
                        continue
                    if ein in seen_eins:
                        continue  # dedup within source
                    seen_eins.add(ein)
                    name = (org.get("name") or "").strip()
                    if not name:
                        skipped += 1
                        log.debug("skip: org without name", extra={"event": "skip",
                                  "source": "irs_990pf", "reason": "no_name", "ein": ein})
                        continue
                    strein = org.get("strein") or ein
                    yield Candidate(
                        name=name,
                        source_class=self.source_class,
                        source_url=f"https://projects.propublica.org/nonprofits/organizations/{ein}",
                        discovered_at=date.today(),
                        dedup_key=norm_name(name),
                        raw={
                            "ein": strein,
                            "ntee_code": org.get("ntee_code"),
                            "subseccd": org.get("subseccd"),
                            "matched_query": query,
                        },
                        hints={"city": org.get("city"), "state": org.get("state")},
                    )
                    yielded += 1
                    if yielded >= limit:
                        break
                page += 1
                if page >= data.get("num_pages", 1):
                    break
        log.info("irs_990pf done", extra={"event": "discover_done", "source": "irs_990pf",
                                          "count": yielded, "skipped": skipped})
