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
import re
from collections import Counter
from datetime import date
from typing import Optional

from pydantic import BaseModel

from .discovery.base import Candidate
from .enrichment.adv import AdvEnricher, AdvFacts
from .enrichment.iapd import IapdEnricher, IapdFacts, facts_from_registry
from .enrichment.sec import SecEnricher, SecFacts, sec_provenance
from .enrichment.thirteenf import ThirteenFEnricher, ThirteenFFacts
from .enrichment.website import WebsiteEnricher, WebsiteFacts
from .observability import get_logger
from .schema import (
    Confidence,
    EmailStatus,
    FamilyOfficeRecord,
    FOType,
    Provenance,
    Signal,
    SourceClass,
    SourceRef,
)
from .text import norm_name
from .validation.firm_type import Classification, classify

log = get_logger("enrichment")

_CONF_RANK = {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1}
_FILLABLE = ("hq_phone", "website", "corporate_linkedin", "hq_city", "hq_state",
             "hq_country", "description", "investment_thesis", "estimated_aum")


def _domain(url: Optional[str]) -> str:
    """Registrable host of a URL, lower-cased, without www. '' if none."""
    m = re.search(r"https?://(?:www\.)?([^/?#]+)", (url or "").strip().lower())
    return m.group(1) if m else ""


def _parse_period(period: Optional[str]) -> Optional[date]:
    """13F reportCalendarOrQuarter 'MM-DD-YYYY' -> date."""
    if not period:
        return None
    m = re.match(r"(\d{2})-(\d{2})-(\d{4})", period.strip())
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    except ValueError:
        return None


# principal-contact fields that cannot be verified from free authoritative sources
# when absent from the firm's own published pages — recorded as could_not_verify when
# blank (never guessed). An email/LinkedIn that the firm's OFFICIAL site publishes is
# extracted by website enrichment and populated WITH provenance, so it never appears
# in this list (the schema rejects a populated field flagged could_not_verify).
_UNVERIFIABLE_CONTACT = ("corporate_linkedin", "principal_linkedin", "principal_email")


def _completeness(r: FamilyOfficeRecord) -> tuple:
    return (bool(r.hq_phone), bool(r.website), len(r.verification_sources), bool(r.hq_city))


def _merge_two(a: FamilyOfficeRecord, b: FamilyOfficeRecord) -> FamilyOfficeRecord:
    """Merge two records for the SAME firm. Keep the higher-confidence / more-complete
    record as the primary and absorb the other's verification sources + any fields it
    is missing (with provenance). Never fabricates: only copies values that already
    carry their own provenance on the donor record."""
    ka = (_CONF_RANK.get(a.record_confidence, 0), _completeness(a))
    kb = (_CONF_RANK.get(b.record_confidence, 0), _completeness(b))
    keep, other = (a, b) if ka >= kb else (b, a)

    seen = {(s.source_class, s.verifies) for s in keep.verification_sources}
    for s in other.verification_sources:
        if (s.source_class, s.verifies) not in seen:
            keep.verification_sources.append(s)
            seen.add((s.source_class, s.verifies))

    for f in _FILLABLE:
        if not getattr(keep, f, None) and getattr(other, f, None):
            setattr(keep, f, getattr(other, f))
            if f in other.provenance and f not in keep.provenance:
                keep.provenance[f] = other.provenance[f]

    keep.record_confidence = keep.compute_record_confidence()
    return keep


def dedupe_records(records: list[FamilyOfficeRecord]) -> tuple[list[FamilyOfficeRecord], list[dict]]:
    """Post-enrichment entity resolution.

    The candidate-stage resolver runs before enrichment, so two lenses that discover the
    same firm under different identifiers (e.g. an SEC 13F CIK and an IAPD CRD) can survive
    as separate candidates and only reveal their shared identity once enrichment resolves a
    website/EIN. This pass merges records that share a strong post-enrichment signal — the
    same website domain, or the same conservatively-normalised name in the same state+country
    — keeping the richer record. Conservative by design: same normalised name alone is NOT
    enough (see DecisionLog D14); it needs a shared domain or matching geography.
    """
    kept: list[FamilyOfficeRecord] = []
    decisions: list[dict] = []
    dom_idx: dict[str, int] = {}
    geo_idx: dict[tuple, int] = {}

    for r in records:
        dom = _domain(r.website)
        geo_key = (norm_name(r.name), (r.hq_state or "").lower(), (r.hq_country or "").lower())
        idx, basis = None, ""
        if dom and dom in dom_idx:
            idx, basis = dom_idx[dom], f"domain:{dom}"
        elif geo_key[0] and (geo_key[1] or geo_key[2]) and geo_key in geo_idx:
            idx, basis = geo_idx[geo_key], "name+state+country"

        if idx is not None:
            merged = _merge_two(kept[idx], r)
            kept[idx] = merged
            decisions.append({"kept": merged.name, "kept_id": merged.fo_id,
                              "merged_out": r.name, "merged_out_id": r.fo_id, "basis": basis})
            log.info("post-enrichment dedup merge", extra={
                "event": "record_merge", "firm": r.name, "kept": merged.fo_id, "basis": basis})
            d2 = _domain(merged.website)
            if d2:
                dom_idx[d2] = idx
            geo_idx[(norm_name(merged.name), (merged.hq_state or "").lower(),
                     (merged.hq_country or "").lower())] = idx
        else:
            idx = len(kept)
            kept.append(r)
            if dom:
                dom_idx[dom] = idx
            if geo_key[0]:
                geo_idx[geo_key] = idx

    return kept, decisions


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
    adv: Optional[AdvFacts] = None
    thirteenf: Optional[ThirteenFFacts] = None
    website: Optional[str] = None
    website_facts: Optional[WebsiteFacts] = None
    wikipedia_bg: Optional[str] = None
    classification: Classification


def enrich_candidate(cand: Candidate, sec_enr: SecEnricher, web_enr: WebsiteEnricher,
                     iapd_enr: IapdEnricher, f13_enr: ThirteenFEnricher,
                     adv_enr: AdvEnricher) -> EnrichedFirm:
    facts = sec_url = sec_hash = None
    cik = cand.identifiers.get("cik") or cand.raw.get("cik")
    if cik:
        try:
            facts, ref = sec_enr.fetch(cik)
            sec_url, sec_hash = ref.url, ref.content_hash
        except Exception as exc:
            log.warning("sec enrich failed", extra={"event": "enrich_warn", "source": "sec",
                                                    "firm": cand.name, "error": str(exc)})

    # SEC Form 13F deep facts: principal (name/title/phone), 13(f) portfolio value (AUM),
    # and recent-investment holdings. Only firms that actually file 13F yield facts.
    thirteenf = None
    if cik:
        try:
            res = f13_enr.fetch(cik)
            if res:
                thirteenf, _ = res
        except Exception as exc:
            log.warning("13f enrich failed", extra={"event": "enrich_warn", "source": "13f",
                                                    "firm": cand.name, "error": str(exc)})

    # IAPD / Form ADV — independent authoritative registration record
    iapd = iapd_url = iapd_hash = None
    if cand.source_class == SourceClass.SEC_IAPD:
        # discovered via the IAPD registry; the registration data is already captured
        iapd = facts_from_registry(
            crd=cand.raw.get("crd", ""), sec_number=cand.raw.get("sec_number"),
            firm_name=cand.name, other_names=cand.raw.get("other_names") or [],
            city=cand.hints.get("city"), state=cand.hints.get("state"),
            country=cand.hints.get("country"))
        iapd_url = cand.source_url
    else:
        try:
            iapd_facts, iapd_ref = iapd_enr.lookup(cand.name)  # name-guarded lookup
            if iapd_facts:
                iapd = iapd_facts
                iapd_url = iapd_facts.report_url
                iapd_hash = iapd_ref.content_hash if iapd_ref else None
        except Exception as exc:
            log.warning("iapd enrich failed", extra={"event": "enrich_warn", "source": "iapd",
                                                     "firm": cand.name, "error": str(exc)})

    # SEC Form ADV deep facts (total AUM + owner-principal) — pure lookup by CRD over the
    # parsed bulk data; only registered advisers with a fresh filing are present.
    crd = cand.raw.get("crd") or (iapd.crd if iapd else None) or cand.identifiers.get("crd")
    adv = adv_enr.lookup(crd)

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
    # constructed-domain resolution for likely family offices that still lack a site
    # (e.g. IAPD-registry-discovered firms) — each candidate domain is fetched and
    # confirmed to contain family-office language before use.
    likely_fo = ("family office" in cand.name.lower()) or bool(iapd and iapd.fo_language)
    if not website and likely_fo:
        try:
            website = web_enr.resolve_domain(cand.name)
        except Exception as exc:
            log.warning("domain resolve failed", extra={"event": "enrich_warn",
                        "source": "website", "firm": cand.name, "error": str(exc)})
    if website:
        try:
            wfacts, _ = web_enr.fetch_site_deep(website)
        except Exception as exc:
            log.warning("site fetch failed", extra={"event": "enrich_warn", "source": "website",
                        "firm": cand.name, "url": website, "error": str(exc)})

    website_text = wfacts.text_excerpt if wfacts else ""
    cls = classify(cand.name, sec_facts=facts, website_text=website_text, iapd=iapd)
    return EnrichedFirm(candidate=cand, sec_facts=facts, sec_url=sec_url, sec_hash=sec_hash,
                        iapd=iapd, iapd_url=iapd_url, iapd_hash=iapd_hash, adv=adv,
                        thirteenf=thirteenf, website=website, website_facts=wfacts,
                        wikipedia_bg=wiki_bg, classification=cls)


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
        # NOTE: a website-stated AUM is intentionally NOT used — scraped marketing figures
        # are unreliable (industry totals, parent-firm numbers, mis-parsed context). AUM is
        # taken only from the authoritative SEC 13F summary below.
        if wf.thesis:
            fields["investment_thesis"] = wf.thesis
            prov["investment_thesis"] = Provenance(
                source_class=SourceClass.FIRM_SITE,
                method="firm website (stated investment approach / mission)", checked_at=as_of,
                source_url=wf.url, confidence=Confidence.MEDIUM)

    # Contact intelligence the firm's OWN site publishes: its contact mailbox(es)
    # and the LinkedIn company page it links. The email is the firm's published
    # outreach inbox (status=RISKY — a firm mailbox, not the principal's
    # personally-verified address); the LinkedIn page is the firm's own page, so
    # the site vouches for both. Nothing is guessed or scraped off-page.
    if e.website_facts and e.website_facts.resolved:
        wf = e.website_facts
        if wf.emails:
            fields["principal_email"] = wf.emails[0]
            prov["principal_email"] = Provenance(
                source_class=SourceClass.FIRM_SITE,
                method="firm website (published contact / mailto link)", checked_at=as_of,
                source_url=wf.url, confidence=Confidence.MEDIUM)
            fields["principal_email_status"] = EmailStatus.RISKY
        if wf.linkedin:
            fields["corporate_linkedin"] = wf.linkedin
            prov["corporate_linkedin"] = Provenance(
                source_class=SourceClass.FIRM_SITE,
                method="LinkedIn company page linked from the official site", checked_at=as_of,
                source_url=wf.url, confidence=Confidence.MEDIUM)

    # SEC Form 13F deep facts — authoritative principal (signatory name/title/phone), the
    # aggregate 13(f) securities value (a dated AUM figure), and recent-investment holdings.
    # Only firms that actually file 13F contribute here; nothing is inferred.
    signals: list[Signal] = []
    tf = e.thirteenf
    period_date = _parse_period(tf.period) if tf else None
    # Freshness gate: a 13F older than ~25 months no longer represents the firm's current
    # principal, AUM, or holdings (the signatory may have left; the value is out of date).
    # A stale filing therefore contributes NOTHING — those fields stay could_not_verify.
    if tf and period_date and (as_of - period_date).days <= 760:
        f13_url = tf.report_url
        sig_prov = Provenance(source_class=SourceClass.SEC_EDGAR,
                              method="SEC Form 13F signature block", checked_at=as_of,
                              source_url=f13_url, confidence=Confidence.HIGH,
                              fetched_at=as_of, content_hash=tf.content_hash)
        if tf.principal_name:
            fields["principal_name"] = tf.principal_name
            prov["principal_name"] = sig_prov
            if tf.principal_title:
                fields["principal_title"] = tf.principal_title
                prov["principal_title"] = sig_prov
            if tf.principal_phone:
                fields["principal_phone"] = tf.principal_phone
                prov["principal_phone"] = sig_prov
        if tf.aum_text:  # authoritative, filed, and now confirmed current
            fields["estimated_aum"] = tf.aum_text
            prov["estimated_aum"] = Provenance(
                source_class=SourceClass.SEC_EDGAR,
                method="SEC Form 13F summary page (aggregate 13(f) securities value)",
                checked_at=as_of, source_url=f13_url, confidence=Confidence.HIGH,
                fetched_at=as_of, content_hash=tf.content_hash)
        if tf.recent_investments_text:
            signals.append(Signal(text=tf.recent_investments_text, source_class=SourceClass.SEC_EDGAR,
                                  event_date=period_date, source_url=f13_url))
        vsources.append(SourceRef(
            source_class=SourceClass.SEC_EDGAR,
            verifies="principal (13F signatory), 13(f) portfolio value, recent holdings",
            accessed_at=as_of, url=f13_url))

    # SEC Form ADV (Item 5.F + Schedule A) — supersedes 13F for AUM (TOTAL regulatory AUM, not
    # just 13(f) securities) and principal (a Schedule A control person/owner — a truer
    # decision-maker than the 13F signatory). The lookup is already freshness-filtered (>=2021).
    if e.adv:
        av = e.adv
        adv_prov = Provenance(source_class=SourceClass.SEC_IAPD,
                              method="SEC Form ADV Part 1A (Item 5.F total AUM / Schedule A control person)",
                              checked_at=as_of, source_url=av.report_url, confidence=Confidence.HIGH)
        if av.aum_text:
            fields["estimated_aum"] = av.aum_text
            prov["estimated_aum"] = adv_prov
        if av.principal_name:
            fields["principal_name"] = av.principal_name
            prov["principal_name"] = adv_prov
            fields.pop("principal_title", None)
            if av.principal_title:
                fields["principal_title"] = av.principal_title
                prov["principal_title"] = adv_prov
            # ADV gives no phone for the owner; drop any 13F-signatory phone (a different person).
            fields.pop("principal_phone", None)
            prov.pop("principal_phone", None)
        vsources.append(SourceRef(
            source_class=SourceClass.SEC_IAPD,
            verifies="total regulatory AUM (ADV Item 5.F), owner/control person (ADV Schedule A)",
            accessed_at=as_of, url=av.report_url))

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
    if e.adv and (e.adv.aum_usd or e.adv.principal_name):
        note = ("estimated_aum is TOTAL regulatory AUM (SEC Form ADV Item 5.F); principal is a "
                "Form ADV Schedule A control person — an owner / executive officer of the firm")
        reviewer_notes = f"{reviewer_notes} | {note}" if reviewer_notes else note
    elif fields.get("principal_name"):
        note = ("principal fields are the firm's SEC Form 13F signatory (a named executive "
                "officer, title exactly as filed — commonly the CCO/General Counsel, not "
                "necessarily the lead investor); estimated_aum is the aggregate 13(f) "
                "securities value, not total assets under management")
        reviewer_notes = f"{reviewer_notes} | {note}" if reviewer_notes else note
    if fields.get("principal_email") and fields.get("principal_email_status") == EmailStatus.RISKY:
        note = ("principal_email is the firm's published contact inbox (official site) — "
                "not the principal's personally-verified address")
        reviewer_notes = f"{reviewer_notes} | {note}" if reviewer_notes else note

    # Honest could_not_verify: contact intelligence that free authoritative sources do not
    # expose (corporate/principal LinkedIn, principal work email) plus principal fields we
    # could not source (firms that file no 13F). Recorded transparently, never guessed —
    # and never for a field that is populated (the schema rejects that contradiction).
    cnv = [f for f in _UNVERIFIABLE_CONTACT if not fields.get(f)]
    for f in ("principal_name", "principal_title", "principal_phone", "estimated_aum"):
        if not fields.get(f):
            cnv.append(f)

    cls = e.classification
    rec = FamilyOfficeRecord(
        fo_id=_fo_id(c), name=name,
        fo_type=cls.fo_type, fo_type_evidence=cls.evidence, fo_type_confidence=cls.confidence,
        discovery_source=disc, verification_sources=vsources, reviewer_notes=reviewer_notes,
        data_as_of=as_of, provenance=prov, signals=signals, could_not_verify=cnv,
        **{k: v for k, v in fields.items() if k != "name"},
    )
    rec.record_confidence = rec.compute_record_confidence()
    return rec


def enrich_and_build(candidates: list[Candidate], as_of: date) -> tuple[list, dict]:
    """Enrich + build all candidates. Returns (records, discovery_report)."""
    sec_enr, web_enr, iapd_enr = SecEnricher(), WebsiteEnricher(), IapdEnricher()
    f13_enr, adv_enr = ThirteenFEnricher(), AdvEnricher()
    records: list[FamilyOfficeRecord] = []
    discovered_by_source: Counter = Counter()
    rejected_by_reason: Counter = Counter()
    qualified_by_source: Counter = Counter()

    for cand in candidates:
        discovered_by_source[cand.source_class.value] += 1
        e = enrich_candidate(cand, sec_enr, web_enr, iapd_enr, f13_enr, adv_enr)
        if not e.classification.qualifies:
            rejected_by_reason[e.classification.reject_reason or "unknown"] += 1
            continue
        rec = build_record(e, as_of)
        if rec is not None:
            records.append(rec)
            qualified_by_source[cand.source_class.value] += 1

    n_before = len(records)
    records, merges = dedupe_records(records)
    if merges:
        log.info("post-enrichment dedup complete", extra={
            "event": "dedup_summary", "before": n_before, "after": len(records),
            "merged": len(merges)})

    report = {
        "discovered_by_source": dict(discovered_by_source),
        "qualified_by_source": dict(qualified_by_source),
        "rejected_by_reason": dict(rejected_by_reason.most_common()),
        "total_discovered": sum(discovered_by_source.values()),
        "qualified_before_dedup": n_before,
        "post_enrichment_merges": merges,
        "total_qualified_pre_gate": len(records),
    }
    return records, report
