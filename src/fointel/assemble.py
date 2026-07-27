"""
Assembly — turn the candidate pool into validated FamilyOfficeRecords.

For each candidate: enrich with authoritative facts (SEC submissions; firm website
resolved via Wikidata for directory firms), classify firm type against the
inclusion standard, then build a record with per-cell provenance and independent
verification sources. Records are NOT published here — that is the release gate's
job (the single publication authority). This module only produces candidate
records + a discovery report; `scripts/build_dataset.py` gates, selects, exports.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from datetime import date
from typing import Optional

from pydantic import BaseModel

from .discovery.base import Candidate
from .enrichment.iapd import IapdEnricher, IapdFacts
from .enrichment.sec import SecEnricher, SecFacts, sec_provenance
from .enrichment.website import WebsiteEnricher, WebsiteFacts
from .observability import get_logger
from .schema import (
    Confidence,
    FamilyOfficeRecord,
    FOType,
    Provenance,
    Signal,
    SourceClass,
    SourceRef,
)
from .validation.firm_type import Classification, classify

log = get_logger("enrichment")


def _fo_id(cand: Candidate) -> str:
    key = cand.dedup_key or cand.name
    return "fo_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


class EnrichedFirm(BaseModel):
    candidate: Candidate
    sec_facts: Optional[SecFacts] = None
    sec_url: Optional[str] = None
    sec_hash: Optional[str] = None
    iapd: Optional[IapdFacts] = None
    iapd_url: Optional[str] = None
    iapd_hash: Optional[str] = None
    website: Optional[str] = None
    website_facts: Optional[WebsiteFacts] = None
    wikipedia_bg: Optional[str] = None
    classification: Classification


def enrich_candidate(cand: Candidate, sec_enr: SecEnricher, web_enr: WebsiteEnricher,
                     iapd_enr: IapdEnricher) -> EnrichedFirm:
    facts = sec_url = sec_hash = None
    cik = cand.identifiers.get("cik") or cand.raw.get("cik")
    if cik:
        try:
            facts, ref = sec_enr.fetch(cik)
            sec_url, sec_hash = ref.url, ref.content_hash
        except Exception as exc:
            log.warning("sec enrich failed", extra={"event": "enrich_warn", "source": "sec",
                                                    "firm": cand.name, "error": str(exc)})

    # IAPD / Form ADV — independent authoritative registration record (name-guarded)
    iapd = iapd_url = iapd_hash = None
    try:
        iapd_facts, iapd_ref = iapd_enr.lookup(cand.name)
        if iapd_facts:
            iapd = iapd_facts
            iapd_url = iapd_facts.report_url
            iapd_hash = iapd_ref.content_hash if iapd_ref else None
    except Exception as exc:
        log.warning("iapd enrich failed", extra={"event": "enrich_warn", "source": "iapd",
                                                 "firm": cand.name, "error": str(exc)})

    website = wfacts = wiki_bg = None
    qid = cand.raw.get("qid")
    title = cand.hints.get("wikipedia_title")
    if cand.source_class == SourceClass.DIRECTORY:
        try:
            if not qid and title:
                qid = web_enr.wikipedia_title_to_qid(title)
            if qid:
                website = web_enr.wikidata_official_site(qid)
            if title:
                wiki_bg = web_enr.wikipedia_intro(title)
        except Exception as exc:
            log.warning("directory enrich failed", extra={"event": "enrich_warn",
                        "source": "directory", "firm": cand.name, "error": str(exc)})
    if facts and facts.website and not website:
        website = facts.website
    if website:
        try:
            wfacts, _ = web_enr.fetch_site_deep(website)
        except Exception as exc:
            log.warning("site fetch failed", extra={"event": "enrich_warn", "source": "website",
                        "firm": cand.name, "url": website, "error": str(exc)})

    website_text = wfacts.text_excerpt if wfacts else ""
    cls = classify(cand.name, sec_facts=facts, website_text=website_text, iapd=iapd)
    return EnrichedFirm(candidate=cand, sec_facts=facts, sec_url=sec_url, sec_hash=sec_hash,
                        iapd=iapd, iapd_url=iapd_url, iapd_hash=iapd_hash,
                        website=website, website_facts=wfacts, wikipedia_bg=wiki_bg,
                        classification=cls)


def build_record(e: EnrichedFirm, as_of: date) -> Optional[FamilyOfficeRecord]:
    """Build a qualifying record (or None). Every populated high-value cell gets provenance."""
    if not e.classification.qualifies:
        return None
    c = e.candidate
    prov: dict[str, Provenance] = {}
    vsources: list[SourceRef] = []
    fields: dict = {}

    def sec_prov(item: str) -> Provenance:
        return Provenance(source_class=SourceClass.SEC_EDGAR,
                          method=f"SEC EDGAR submissions ({item})", checked_at=as_of,
                          source_url=e.sec_url, confidence=Confidence.HIGH,
                          fetched_at=as_of, content_hash=e.sec_hash, snapshot_path=None)

    # name (anchor) — verified by the strongest authoritative source available
    name = (e.sec_facts.legal_name if e.sec_facts and e.sec_facts.legal_name else c.name)
    fields["name"] = name
    if e.sec_facts:
        prov["name"] = sec_prov("registrant name")
    elif e.website_facts and e.website_facts.resolved:
        prov["name"] = Provenance(source_class=SourceClass.FIRM_SITE, method="firm website",
                                  checked_at=as_of, source_url=e.website, confidence=Confidence.MEDIUM)

    # SEC authoritative facts: geography + firm phone
    if e.sec_facts:
        f = e.sec_facts
        if f.city:
            fields["hq_city"] = f.city
        if f.state:
            fields["hq_state"] = f.state
        if f.country:
            fields["hq_country"] = f.country
            prov["hq_country"] = sec_prov("business address")
        if f.phone:
            fields["hq_phone"] = f.phone
            prov["hq_phone"] = sec_prov("business phone")
        vsources.append(SourceRef(source_class=SourceClass.SEC_EDGAR,
                                  verifies="firm existence, address, phone, EIN",
                                  accessed_at=as_of, url=e.sec_url))

    # IAPD / Form ADV — independent authoritative registration record
    if e.iapd:
        ip = e.iapd
        vsources.append(SourceRef(source_class=SourceClass.SEC_IAPD,
                                  verifies="firm registration, family-office status, type",
                                  accessed_at=as_of, url=e.iapd_url))
        iapd_prov = Provenance(source_class=SourceClass.SEC_IAPD, method="IAPD registration record",
                               checked_at=as_of, source_url=e.iapd_url, confidence=Confidence.HIGH,
                               fetched_at=as_of, content_hash=e.iapd_hash)
        if "name" not in prov:
            prov["name"] = iapd_prov
        if "hq_country" not in fields and ip.country:
            fields["hq_country"] = ip.country
            prov["hq_country"] = iapd_prov
        if "hq_city" not in fields and ip.city:
            fields["hq_city"] = ip.city
        if "hq_state" not in fields and ip.state:
            fields["hq_state"] = ip.state

    # website: authoritative corroboration + description/AUM
    if e.website_facts and e.website_facts.resolved:
        wf = e.website_facts
        fields["website"] = wf.url or e.website
        prov["website"] = Provenance(source_class=SourceClass.FIRM_SITE, method="fetched firm website",
                                     checked_at=as_of, source_url=wf.url or e.website,
                                     confidence=Confidence.HIGH)
        if wf.fo_language:
            vsources.append(SourceRef(source_class=SourceClass.FIRM_SITE,
                                      verifies="family-office status, type", accessed_at=as_of,
                                      url=wf.url or e.website))
        if wf.description:
            fields["description"] = wf.description
            prov["description"] = Provenance(source_class=SourceClass.FIRM_SITE,
                                             method="website meta description", checked_at=as_of,
                                             source_url=wf.url, confidence=Confidence.MEDIUM)
        if wf.aum_text:
            fields["estimated_aum"] = wf.aum_text
            prov["estimated_aum"] = Provenance(source_class=SourceClass.FIRM_SITE,
                                               method="stated on firm website", checked_at=as_of,
                                               source_url=wf.url, confidence=Confidence.MEDIUM)

    # Wikipedia background -> description only if we have nothing better (cited as background)
    if "description" not in fields and e.wikipedia_bg:
        fields["description"] = e.wikipedia_bg[:400]
        prov["description"] = Provenance(source_class=SourceClass.DIRECTORY,
                                         method="Wikipedia intro (background only)", checked_at=as_of,
                                         source_url=None, confidence=Confidence.LOW,
                                         note="background context; not used to verify FO status")

    # geography fallback to discovery hints (e.g. 990-PF city/state from the IRS filing,
    # directory country) — only when no authoritative source already supplied it.
    h = c.hints
    if "hq_state" not in fields and h.get("state"):
        fields["hq_state"] = h["state"]
    if "hq_city" not in fields and h.get("city"):
        fields["hq_city"] = h["city"]
    if "hq_country" not in fields:
        country = h.get("country") or ("United States" if fields.get("hq_state") else None)
        if country:
            fields["hq_country"] = country
            prov["hq_country"] = Provenance(
                source_class=c.source_class, method="discovery-source filing/record address",
                checked_at=as_of, confidence=Confidence.MEDIUM,
                note="location from the discovery source (e.g. IRS 990-PF / directory)")

    # same-source justification whenever any verification source shares the discovery class
    # (e.g. discovered via SEC 13F full-text search, verified via the distinct SEC submissions
    # registration record). Independent sources (IAPD, firm website) still raise confidence.
    reviewer_notes = None
    disc = c.source_class
    if any(s.source_class == disc for s in vsources):
        reviewer_notes = ("same-source: discovered via SEC 13F full-text search on filings; "
                          "verified via the distinct SEC submissions registration record and the "
                          "firm's regulatory self-identification as a family office")

    cls = e.classification
    rec = FamilyOfficeRecord(
        fo_id=_fo_id(c), name=name,
        fo_type=cls.fo_type, fo_type_evidence=cls.evidence, fo_type_confidence=cls.confidence,
        discovery_source=disc, verification_sources=vsources, reviewer_notes=reviewer_notes,
        data_as_of=as_of, provenance=prov,
        **{k: v for k, v in fields.items() if k != "name"},
    )
    rec.record_confidence = rec.compute_record_confidence()
    return rec


def enrich_and_build(candidates: list[Candidate], as_of: date) -> tuple[list, dict]:
    """Enrich + build all candidates. Returns (records, discovery_report)."""
    sec_enr, web_enr, iapd_enr = SecEnricher(), WebsiteEnricher(), IapdEnricher()
    records: list[FamilyOfficeRecord] = []
    discovered_by_source: Counter = Counter()
    rejected_by_reason: Counter = Counter()
    qualified_by_source: Counter = Counter()

    for cand in candidates:
        discovered_by_source[cand.source_class.value] += 1
        e = enrich_candidate(cand, sec_enr, web_enr, iapd_enr)
        if not e.classification.qualifies:
            rejected_by_reason[e.classification.reject_reason or "unknown"] += 1
            continue
        rec = build_record(e, as_of)
        if rec is not None:
            records.append(rec)
            qualified_by_source[cand.source_class.value] += 1

    report = {
        "discovered_by_source": dict(discovered_by_source),
        "qualified_by_source": dict(qualified_by_source),
        "rejected_by_reason": dict(rejected_by_reason.most_common()),
        "total_discovered": sum(discovered_by_source.values()),
        "total_qualified_pre_gate": len(records),
    }
    return records, report
