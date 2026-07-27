"""
Firm-type classification (Rule 2) — enforces config/inclusion_standard.md.

A firm qualifies ONLY with affirmative family-office evidence from an
**authoritative** source (a SEC filing, or the firm's own website) — never from a
name alone or a discovery-only reference (Wikipedia/Wikidata). Non-qualifying
organisations (public companies, funds, banks, pensions, religious/educational
orgs, individual trustees, bare foundations) are rejected with a reason.

Type (SFO / MFO / Undetermined) is set from explicit language where available and
honestly left Undetermined otherwise. Confidence rises with independent
corroboration and never exceeds the evidence.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel

from ..enrichment.sec import SecFacts
from ..schema import Confidence, FOType

# High-precision non-family-office signals (inclusion_standard §6). Matched against
# name + any corroboration text, so "Family Office University Network" is rejected.
_REJECT_PATTERNS: list[tuple[str, str]] = [
    (r"\b(pension|retirement|401\s*k|403\s*b|profit\s*sharing|esop|benefit plan|welfare fund)\b",
     "employee benefit / pension plan"),
    (r"\b(insurance|assurance)\b", "insurance entity"),
    (r"\b(bancorp|bancshares|bankshares|savings bank|credit union)\b", "bank / depository"),
    (r"\b(university|college|school district|academy|seminary)\b", "educational institution"),
    (r"\b(church|diocese|archdiocese|ministries|ministry|synagogue|temple|congregation|parish|"
     r"catholic|baptist|methodist|presbyterian|lutheran|episcopal|vincentian)\b",
     "religious organization"),
    (r"\b(hospital|health system|medical center|healthcare system)\b", "healthcare institution"),
    (r"\b(city of|county of|state of|municipal|water district|school board)\b",
     "government / municipal entity"),
    (r"\b(association|federation|society|league|network)\b",
     "membership / association / network, not a family office"),
]

_MFO_LANG = re.compile(r"multi[- ]?family (office|)", re.IGNORECASE)
_SFO_LANG = re.compile(r"single[- ]?family office", re.IGNORECASE)
_FO_LANG = re.compile(r"family office", re.IGNORECASE)


class Classification(BaseModel):
    qualifies: bool
    fo_type: FOType
    evidence: Optional[str] = None       # -> record.fo_type_evidence (only when qualifies)
    confidence: Confidence = Confidence.LOW
    reject_reason: Optional[str] = None  # -> audit reason (when not qualifying)


def _reject(reason: str) -> Classification:
    return Classification(qualifies=False, fo_type=FOType.UNDETERMINED, reject_reason=reason)


def classify(name: str, sec_facts: Optional[SecFacts] = None, website_text: str = "",
             iapd=None, extra_texts: Optional[list[str]] = None) -> Classification:
    lname = name.lower()
    web = (website_text or "").lower()
    iapd_text = " ".join([iapd.firm_name] + iapd.other_names).lower() if iapd else ""
    combined = " ".join([lname, web, iapd_text] + [t.lower() for t in (extra_texts or [])])

    # 1. hard rejects
    if sec_facts and sec_facts.is_public_company:
        return _reject("public company (SEC tickers/exchanges present)")
    for pattern, reason in _REJECT_PATTERNS:
        if re.search(pattern, combined):
            return _reject(reason)
    if re.search(r"\btrustee\b", lname) and "family office" not in lname:
        return _reject("individual trustee, not a family-office firm")

    # 2. affirmative FO evidence from AUTHORITATIVE sources (name alone is insufficient)
    name_fo = bool(_FO_LANG.search(lname))
    web_fo = bool(_FO_LANG.search(web))
    iapd_fo = bool(iapd and iapd.fo_language)
    sources: list[str] = []
    if name_fo and sec_facts is not None:
        sources.append("SEC 13F filer self-identifying as a family office")
    if iapd_fo:
        sources.append("SEC Form ADV / IAPD registration names it a family office")
    if web_fo:
        sources.append("firm website describes itself as a family office")
    if not sources:
        return _reject("no affirmative family-office evidence from an authoritative source "
                       "(name / discovery-only references are insufficient)")

    # 3. type from explicit language (incl. IAPD aliases); honest Undetermined otherwise
    iapd_hint = iapd.fo_type_hint if iapd else None
    if _MFO_LANG.search(combined) or iapd_hint == "MFO":
        fo_type, type_basis = FOType.MFO, "multi-family language"
    elif _SFO_LANG.search(combined) or iapd_hint == "SFO":
        fo_type, type_basis = FOType.SFO, "single-family language"
    else:
        fo_type, type_basis = FOType.UNDETERMINED, "single vs multi family not established"

    confidence = Confidence.HIGH if len(sources) >= 2 else Confidence.MEDIUM
    evidence = "; ".join(sources) + f"; type: {type_basis}"
    return Classification(qualifies=True, fo_type=fo_type, evidence=evidence,
                          confidence=confidence, reject_reason=None)
