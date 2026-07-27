"""
IAPD / Form ADV enrichment — the SEC investment-adviser registration record.

IAPD (IARD) is a different filing system from EDGAR 13F, so it is a genuinely
INDEPENDENT authoritative source for a firm discovered via 13F full-text search:
it confirms the registered entity, its office address, active/inactive status, and
— critically — its registered names/aliases, which often state the family-office
nature and single/multi type (e.g. "PATHSTONE FAMILY OFFICE, LLC").

A name-match guard prevents ever attaching a different firm's record.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel
from rapidfuzz import fuzz

from ..evidence import EvidenceRef
from ..http import HttpClient
from ..observability import get_logger
from ..schema import Confidence, Provenance, SourceClass
from ..text import norm_name

log = get_logger("enrichment")

_FO = re.compile(r"family office", re.IGNORECASE)
_SFO = re.compile(r"single[- ]?family", re.IGNORECASE)
_MFO = re.compile(r"multi[- ]?family", re.IGNORECASE)


class IapdFacts(BaseModel):
    crd: str
    sec_number: Optional[str] = None
    firm_name: str
    other_names: list[str] = []
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    active: bool = False
    fo_language: bool = False           # a registered name states "family office"
    fo_type_hint: Optional[str] = None  # "SFO" / "MFO" from aliases

    @property
    def report_url(self) -> str:
        return f"https://adviserinfo.sec.gov/firm/summary/{self.crd}"


class IapdEnricher:
    SEARCH = "https://api.adviserinfo.sec.gov/search/firm"

    def __init__(self, match_threshold: int = 82):
        self.http = HttpClient(user_agent="Mozilla/5.0", accept="application/json",
                               timeout=20, max_attempts=2)
        self.match_threshold = match_threshold

    def lookup(self, firm_name: str) -> tuple[Optional[IapdFacts], Optional[EvidenceRef]]:
        try:
            resp, ref = self.http.get_with_evidence(
                self.SEARCH, params={"query": firm_name, "hits": 3, "includeInactive": "true"})
        except Exception as exc:
            log.warning("iapd lookup failed", extra={"event": "enrich_warn", "source": "iapd",
                        "firm": firm_name, "error": str(exc)})
            return None, None
        hits = ((resp.json().get("hits") or {}).get("hits")) or []
        target = norm_name(firm_name)
        for hit in hits:
            src = hit.get("_source", {})
            names = [src.get("firm_name", "")] + (src.get("firm_other_names") or [])
            # name-match guard: accept only if a registered name matches the query well
            if not any(fuzz.token_set_ratio(target, norm_name(n)) >= self.match_threshold
                       for n in names if n):
                continue
            return self._parse(src), ref
        return None, ref

    @staticmethod
    def _parse(src: dict) -> IapdFacts:
        names = [src.get("firm_name", "")] + (src.get("firm_other_names") or [])
        joined = " ".join(names)
        addr = {}
        try:
            addr = (json.loads(src.get("firm_ia_address_details") or "{}")
                    ).get("officeAddress", {}) or {}
        except (json.JSONDecodeError, TypeError):
            pass
        type_hint = "SFO" if _SFO.search(joined) else ("MFO" if _MFO.search(joined) else None)
        return IapdFacts(
            crd=str(src.get("firm_source_id") or ""),
            sec_number=src.get("firm_ia_full_sec_number") or None,
            firm_name=src.get("firm_name", ""),
            other_names=[n for n in (src.get("firm_other_names") or []) if n],
            city=addr.get("city") or None,
            state=addr.get("state") or None,
            country=addr.get("country") or None,
            active=(src.get("firm_ia_scope") == "ACTIVE"),
            fo_language=bool(_FO.search(joined)),
            fo_type_hint=type_hint,
        )


def facts_from_registry(crd: str, sec_number: Optional[str], firm_name: str,
                        other_names: list[str], city: Optional[str], state: Optional[str],
                        country: Optional[str]) -> IapdFacts:
    """Build IapdFacts from data already captured by IAPD discovery (no re-fetch)."""
    joined = " ".join([firm_name] + other_names)
    return IapdFacts(
        crd=crd, sec_number=sec_number, firm_name=firm_name, other_names=other_names,
        city=city, state=state, country=country, active=True,
        fo_language=bool(_FO.search(joined)),
        fo_type_hint="SFO" if _SFO.search(joined) else ("MFO" if _MFO.search(joined) else None))


def iapd_provenance(facts: IapdFacts, ref: Optional[EvidenceRef], item: str,
                    checked_at) -> Provenance:
    return Provenance(
        source_class=SourceClass.SEC_IAPD, method=f"SEC IAPD / Form ADV ({item})",
        checked_at=checked_at, source_url=facts.report_url, confidence=Confidence.HIGH,
        fetched_at=ref.fetched_at if ref else None,
        content_hash=ref.content_hash if ref else None)
