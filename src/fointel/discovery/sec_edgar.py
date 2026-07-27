"""
Discovery source 1 — SEC EDGAR (regulatory lens).

Uses EDGAR full-text search to find entities whose filings mention "family office"
in institutional-investor forms (13F holdings reports, SC 13D/G ownership stakes).
These are real investment entities managing family wealth — a high-signal FO lens.

Discovery only: it surfaces a firm + CIK + location. Authoritative firm facts
(address, phone, former names) are pulled later by the enrichment layer via
data.sec.gov/submissions — kept separate so discovery never doubles as proof.
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

_CIK_SUFFIX = re.compile(r"\s*\(CIK\s*\d+\)\s*$", re.IGNORECASE)


def _clean_name(display_name: str) -> str:
    """'EMFO, LLC  (CIK 0001859434)' -> 'EMFO, LLC'."""
    return _CIK_SUFFIX.sub("", display_name).strip()


class SecEdgarSource(DiscoverySource):
    source_class = SourceClass.SEC_EDGAR
    SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"

    def __init__(self, query: str = '"family office"',
                 forms: tuple[str, ...] = ("13F-HR", "SC 13D", "SC 13G")):
        # SEC asks for a descriptive UA (set in .env); polite 0.5s pause is default.
        self.http = HttpClient()
        self.query = query
        self.forms = forms

    def discover(self, limit: int) -> Iterator[Candidate]:
        seen_ciks: set[str] = set()
        yielded = 0
        for form in self.forms:
            frm = 0
            while yielded < limit:
                data = self.http.get_json(
                    self.SEARCH_URL, params={"q": self.query, "forms": form, "from": frm}
                )
                hits = data.get("hits", {}).get("hits", [])
                if not hits:
                    break
                total = data.get("hits", {}).get("total", {}).get("value", 0)
                for hit in hits:
                    src = hit.get("_source", {})
                    ciks = src.get("ciks") or []
                    if not ciks:
                        continue
                    cik = str(ciks[0]).lstrip("0") or ciks[0]
                    if cik in seen_ciks:
                        continue
                    seen_ciks.add(cik)
                    names = src.get("display_names") or []
                    if not names:
                        continue
                    name = _clean_name(names[0])
                    if not name:
                        continue
                    location = (src.get("biz_locations") or [None])[0]
                    state = (src.get("biz_states") or [None])[0]
                    yield Candidate(
                        name=name,
                        source_class=self.source_class,
                        source_url=(f"https://www.sec.gov/cgi-bin/browse-edgar?action="
                                    f"getcompany&CIK={cik}&type={form}"),
                        discovered_at=date.today(),
                        dedup_key=norm_name(name),
                        raw={
                            "cik": cik,
                            "matched_form": form,
                            "accession": src.get("adsh"),
                            "file_date": src.get("file_date"),
                            "period_ending": src.get("period_ending"),
                        },
                        hints={"city_state": location, "state": state, "cik": cik},
                    )
                    yielded += 1
                    if yielded >= limit:
                        break
                frm += len(hits)
                if frm >= total:
                    break
            log.info("sec_edgar form scanned", extra={"event": "discover", "source": "sec_edgar",
                                                       "form": form, "yielded_so_far": yielded})
        log.info("sec_edgar done", extra={"event": "discover_done", "source": "sec_edgar",
                                          "count": yielded})
