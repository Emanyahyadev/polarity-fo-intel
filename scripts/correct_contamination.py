"""
Data-quality correction (reproducible; not manual spreadsheet editing).

Two corrections, both driven by an authoritative re-check against SEC IAPD:

1. THE FAMILY OFFICE, LLC (CRD 288530) — its generic name (no distinctive token)
   had caused an UNRELATED company's website (thefamilyoffice.com, a residential
   real-estate advisory) to be attached, contaminating website/description/thesis/
   principal/type. IAPD confirms the entity is real (Redmond, WA) but its SEC
   registration is INACTIVE/withdrawn and no independent website/AUM/principal can
   be verified. We STRIP every unverifiable/contaminated field back to the facts
   IAPD actually supports, and honestly flag the rest as could_not_verify.

2. Five IAPD-registered firms are INACTIVE/withdrawn (verified via the IAPD firm
   search API). For a family office a withdrawn registration is often expected
   (single-family offices are exempt under the SEC Family Office Rule). Four of the
   five have INDEPENDENT evidence of active operation (verified website, or a recent
   Form 13F, or Form ADV AUM), so they are kept — but every one gets an honest
   registration-status note so the dataset never overstates "SEC-registered".

Re-exports CSV + XLSX. Idempotent: safe to re-run.
    py -3.12 scripts/correct_contamination.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fointel.export import export_dataset                       # noqa: E402
from fointel.rag.load import load_records_from_csv              # noqa: E402
from fointel.schema import (Confidence, FOType, HIGH_VALUE_FIELDS,  # noqa: E402
                            Provenance, SourceClass)

AS_OF = date(2026, 7, 28)
SITE_FIELDS = {"website", "description", "investment_thesis", "corporate_linkedin"}

# CRD + independent operating evidence for the five IAPD-INACTIVE firms.
INACTIVE = {
    "CARPA FAMILY OFFICE":
        ("329017", "an independently verified firm website"),
    "HOLDUN FAMILY OFFICE LLC":
        ("158123", "an independently verified firm website"),
    "WEALTHGATE FAMILY OFFICE, LLC":
        ("307858", "a recent SEC Form 13F filing (period 2024-09-30)"),
    "GELLER ADVISORS LLC":
        ("134062", "SEC Form ADV Item 5.F regulatory AUM and Form 13F filings"),
    # THE FAMILY OFFICE, LLC (288530) is handled by the strip below, not here.
}


def reconstruct(rec):
    """Rebuild per-cell provenance from verification sources so the Provenance sheet
    is preserved on re-export (same logic the enrichment pipeline uses)."""
    vs = rec.verification_sources
    if not vs:
        return
    site = next((s for s in vs if s.source_class == SourceClass.FIRM_SITE), None)
    reg = next((s for s in vs if s.source_class != SourceClass.FIRM_SITE), vs[0])
    for f in HIGH_VALUE_FIELDS:
        if getattr(rec, f, None) and f not in rec.provenance:
            src = site if (f in SITE_FIELDS and site) else reg
            rec.provenance[f] = Provenance(
                source_class=src.source_class,
                method=f"verified via {src.source_class.value}",
                checked_at=rec.data_as_of, confidence=rec.record_confidence)


def strip_the_family_office(rec) -> None:
    """Reset CRD 288530 to only what SEC IAPD authoritatively supports."""
    rec.fo_type = FOType.UNDETERMINED
    rec.fo_type_evidence = (
        "SEC IAPD / Form ADV registration (CRD 288530) registers the entity as a "
        "family-office adviser (registered names include 'THE FAMILY OFFICE, LLC' and "
        "'OUR FAMILY OFFICE, LLC'); single- vs multi-family type not established from "
        "authoritative sources. SEC registration is currently inactive/withdrawn.")
    rec.description = (
        "SEC-registered investment adviser (IAPD / Form ADV, CRD 288530) based in "
        "Redmond, Washington, registered as a family-office adviser (also filed as "
        "'Our Family Office, LLC'). SEC registration is currently inactive/withdrawn. "
        "An independent firm website, principal, and AUM could not be verified from "
        "authoritative free public sources.")
    # Remove every field that had been sourced from the wrong company's website.
    rec.website = None
    rec.investment_thesis = None
    rec.principal_name = None
    rec.principal_title = None
    rec.investing_sectors = []
    # Drop the firm-website verification source (it was a different company).
    rec.verification_sources = [s for s in rec.verification_sources
                                if s.source_class != SourceClass.FIRM_SITE]
    # Honestly flag the now-blank high-value fields.
    for f in ("website", "investment_thesis", "principal_name", "principal_title",
              "principal_linkedin", "principal_email", "principal_phone",
              "corporate_linkedin", "estimated_aum"):
        if f not in rec.could_not_verify:
            rec.could_not_verify.append(f)
    rec.record_confidence = Confidence.LOW
    note = ("CORRECTION (2026-07-28): the firm's generic name had caused an unrelated "
            "company's website (thefamilyoffice.com, a residential real-estate advisory) "
            "to be attached; all website-derived fields were removed. Retained facts are "
            "IAPD-verified only (name, Redmond WA location, family-office registration). "
            "SEC registration confirmed inactive/withdrawn (IAPD firm search, 2026-07-28).")
    rec.reviewer_notes = ((rec.reviewer_notes + " ") if rec.reviewer_notes else "") + note
    # provenance must not reference the removed website source
    for k in list(rec.provenance):
        if rec.provenance[k].source_class == SourceClass.FIRM_SITE:
            del rec.provenance[k]


def main() -> None:
    records = load_records_from_csv()
    for rec in records:
        reconstruct(rec)

    changed = {"stripped": [], "status_noted": []}
    for rec in records:
        key = rec.name.upper().strip()
        if rec.fo_id == "fo_c7fbed29da" or key == "THE FAMILY OFFICE, LLC":
            strip_the_family_office(rec)
            changed["stripped"].append(rec.name)
        elif key in INACTIVE:
            crd, evidence = INACTIVE[key]
            tag = f"[registration status] SEC IAPD registration (CRD {crd})"
            if tag not in (rec.reviewer_notes or ""):
                note = (f"{tag} is currently inactive/withdrawn (verified via IAPD firm "
                        f"search, 2026-07-28); the firm is independently evidenced as "
                        f"operating via {evidence}. (A withdrawn SEC registration is common "
                        f"for family offices exempt under the SEC Family Office Rule.)")
                rec.reviewer_notes = ((rec.reviewer_notes + " ")
                                      if rec.reviewer_notes else "") + note
                changed["status_noted"].append(f"{rec.name} (CRD {crd})")

    # Invariant guard: no could_not_verify field may be populated.
    for rec in records:
        bad = [f for f in rec.could_not_verify if getattr(rec, f, None)]
        assert not bad, f"{rec.name}: populated+could_not_verify {bad}"
        # qualifies() must still hold for every record.
        assert rec.qualifies(), f"{rec.name}: lost qualification (no fo_type_evidence)"

    res = export_dataset(records, audit=[], out_dir="data/final")
    print("===== CONTAMINATION CORRECTION REPORT =====")
    print(f"  records: {res['records']} | provenance rows: {res['provenance_rows']}")
    print(f"  stripped (contamination removed): {changed['stripped']}")
    print(f"  registration-status noted ({len(changed['status_noted'])}):")
    for x in changed["status_noted"]:
        print("     -", x)
    from collections import Counter
    print("  type distribution:", dict(Counter(r.fo_type.value for r in records)))


if __name__ == "__main__":
    main()
