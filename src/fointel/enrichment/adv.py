"""
SEC Form ADV (Part 1A) deep enrichment — total AUM + owner-principal for registered
family offices that do NOT file 13F.

The IAPD *search* API exposes registration but not Item 5 (AUM) or Schedule A (owners);
those live in the SEC's bulk Form ADV data set. `scripts/parse_adv_bulk.py` parses that
(authoritative, free) download once into `data/adv/adv_facts.json`, keyed by CRD, keeping
only reasonably fresh filings (>= 2021). This enricher is a pure lookup over that file:

  * Item 5.F(2)(c) -> **total regulatory AUM** (more complete than the 13F 13(f)-only value)
  * Schedule A control person -> the firm's **owner / executive** (a decision-maker, not
    merely the 13F signatory)

Nothing is inferred: a CRD absent from the lookup yields no facts (the firm keeps its
honest could_not_verify). Reproduce the lookup from the SEC source via the parse script.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from ..observability import get_logger

log = get_logger("enrichment")

_DEFAULT_PATH = "data/adv/adv_facts.json"


class AdvFacts(BaseModel):
    crd: str
    aum_usd: Optional[int] = None
    filing_year: Optional[int] = None
    principal_name: Optional[str] = None
    principal_title: Optional[str] = None
    legal_name: Optional[str] = None

    @property
    def report_url(self) -> str:
        return f"https://adviserinfo.sec.gov/firm/summary/{self.crd}"

    @property
    def aum_text(self) -> Optional[str]:
        if not self.aum_usd:
            return None
        v = self.aum_usd
        human = f"${v/1e9:.2f}B" if v >= 1e9 else (f"${v/1e6:.0f}M" if v >= 1e6 else f"${v:,}")
        yr = f" as of {self.filing_year}" if self.filing_year else ""
        return f"{human} total regulatory AUM (SEC Form ADV Item 5.F{yr})"


class AdvEnricher:
    def __init__(self, path: str = _DEFAULT_PATH):
        p = Path(path)
        try:
            self._data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("adv lookup unreadable", extra={"event": "enrich_warn",
                        "source": "adv", "error": str(exc)})
            self._data = {}

    def lookup(self, crd: Optional[str]) -> Optional[AdvFacts]:
        if not crd:
            return None
        r = self._data.get(str(crd))
        if not r:
            return None
        return AdvFacts(crd=str(crd), aum_usd=r.get("aum_usd"), filing_year=r.get("filing_year"),
                        principal_name=r.get("principal_name"),
                        principal_title=r.get("principal_title"), legal_name=r.get("legal_name"))
