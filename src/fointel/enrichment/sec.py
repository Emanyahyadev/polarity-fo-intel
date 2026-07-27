"""
SEC enrichment — authoritative firm facts from data.sec.gov/submissions.

For any candidate with a CIK, the SEC submissions API returns the entity's legal
name, business address, main phone, EIN, former names, and filing history — all
authoritative (filed with a regulator). This is the strongest verification source
in the pipeline and supplies real, checkable contact intelligence.

Every fetch is snapshotted (content hash) for reproducible provenance.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from ..evidence import EvidenceRef
from ..http import HttpClient
from ..observability import get_logger
from ..schema import Confidence, Provenance, SourceClass

log = get_logger("enrichment")

_US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC", "PR",
}


def _format_phone(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"+1 ({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return raw.strip() or None


def _format_ein(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if digits in ("999999999", "000000000"):  # SEC placeholders for "not provided"
        return None
    return f"{digits[:2]}-{digits[2:]}" if len(digits) == 9 else (raw or None)


class SecFacts(BaseModel):
    cik: str
    legal_name: Optional[str] = None
    street1: Optional[str] = None
    street2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    zipcode: Optional[str] = None
    phone: Optional[str] = None
    ein: Optional[str] = None
    website: Optional[str] = None
    sic: Optional[str] = None
    sic_description: Optional[str] = None
    entity_type: Optional[str] = None
    is_public_company: bool = False        # has tickers/exchanges -> not a family office
    former_names: list[str] = []
    forms_filed: list[str] = []


def sec_provenance(ref: EvidenceRef, item: str,
                   confidence: Confidence = Confidence.HIGH) -> Provenance:
    """Provenance for a value taken from an SEC submissions record."""
    return Provenance(
        source_class=SourceClass.SEC_EDGAR, method=f"SEC EDGAR submissions ({item})",
        checked_at=ref.fetched_at, source_url=ref.url, confidence=confidence,
        fetched_at=ref.fetched_at, content_hash=ref.content_hash,
        snapshot_path=ref.snapshot_path)


class SecEnricher:
    SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"

    def __init__(self):
        self.http = HttpClient()

    def fetch(self, cik: str) -> tuple[SecFacts, EvidenceRef]:
        cik10 = str(cik).lstrip("0").zfill(10)
        resp, ref = self.http.get_with_evidence(self.SUBMISSIONS.format(cik=cik10), ext="json")
        return self._parse(cik10, resp.json()), ref

    @staticmethod
    def _parse(cik10: str, d: dict) -> SecFacts:
        addresses = d.get("addresses") or {}
        addr = addresses.get("business") or addresses.get("mailing") or {}
        state_or_country = (addr.get("stateOrCountry") or "").upper() or None
        if state_or_country in _US_STATES:
            state, country = state_or_country, "United States"
        elif state_or_country:
            state, country = None, addr.get("stateOrCountryDescription") or state_or_country
        else:
            state, country = None, None
        recent = ((d.get("filings") or {}).get("recent") or {}).get("form") or []
        return SecFacts(
            cik=cik10,
            legal_name=d.get("name") or None,
            street1=addr.get("street1") or None,
            street2=addr.get("street2") or None,
            city=addr.get("city") or None,
            state=state,
            country=country,
            zipcode=addr.get("zipCode") or None,
            phone=_format_phone(d.get("phone")),
            ein=_format_ein(d.get("ein")),
            website=(d.get("website") or "").strip() or None,
            sic=(d.get("sic") or "") or None,
            sic_description=(d.get("sicDescription") or "").strip() or None,
            entity_type=(d.get("entityType") or "").strip() or None,
            is_public_company=bool(d.get("tickers") or d.get("exchanges")),
            former_names=[fn.get("name") for fn in (d.get("formerNames") or []) if fn.get("name")],
            forms_filed=sorted(set(recent))[:25],
        )
