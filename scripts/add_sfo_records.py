"""
SFO expansion, phase 2 — append the website-VERIFIED single-family offices (from
scripts/verify_sfo_targets.py, human-reviewed) to the canonical store.

Same standard as the existing directory SFOs (D24/D25): classification rests on an
explicit single-family self-identification quote from the firm's OWN website; AUM and
contact fields are honest could_not_verify (no free authoritative source); the family
principal is NOT written into principal_name unless the site names them as the office's
decision-maker (Dell/Bloomberg are the families served, not the office heads).

Operates on data/final/records.json (lossless store) + audit.json; re-exports CSV/XLSX
and regenerates embeddings. Idempotent (skips if fo_id/domain already present).
    py -3.12 scripts/add_sfo_records.py
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fointel.export import export_dataset                        # noqa: E402
from fointel.rag.index import precompute_and_save                # noqa: E402
from fointel.rag.load import load_records_from_store             # noqa: E402
from fointel.schema import (AuditEntry, Confidence, FamilyOfficeRecord,  # noqa: E402
                            FOType, Provenance, SourceClass, SourceRef)

AS_OF = date(2026, 7, 29)
SITE = SourceClass.FIRM_SITE
DIR = SourceClass.DIRECTORY

BASE_NOTE = ("Discovered via the curated/notable-reference lens (Wikipedia's family-office "
             "listings); classification and firm identity verified against the firm's own "
             "authoritative website (single verification source). AUM and individual contact "
             "details are not available from free authoritative sources and are left "
             "could_not_verify. The family the office serves is named in the classification "
             "evidence; it is deliberately NOT recorded as the office's principal, because the "
             "site does not name the office's own decision-maker.")

NEW = [
    dict(
        name="MSD Capital, L.P.",
        website="https://www.msdcapital.com/",
        city="New York", state="NY", country="United States",
        desc=("Private investment firm that exclusively manages the assets of Michael S. Dell "
              "and his family."),
        thesis=("MSD Capital utilizes a multi-disciplinary investment strategy focused on "
                "maximizing long-term capital appreciation by making investments across the "
                "globe in the equities of public and private companies, credit, real estate "
                "and other asset classes and securities."),
        evidence=('Firm\'s own website self-identifies as a single-family office: "Established '
                  'in 1998, exclusively manages the assets of Michael S. Dell and his family." '
                  "Discovered via a non-SEC curated-reference lens; classification and firm "
                  "identity verified against the firm's own website."),
        note=BASE_NOTE + " Wikipedia's family-office category lists this firm under its later "
             "corporate name (DFO Management, LLC); the firm's own site presents as MSD "
             "Capital, L.P., and the record uses the site's own name — identity verified "
             "against that site.",
    ),
    dict(
        name="Willett Advisors LLC",
        website="https://www.willettadvisors.com/",
        city="New York", state="NY", country="United States",
        desc="Manages the philanthropic assets of Michael R. Bloomberg.",
        thesis=("The firm's objective is to achieve long-term capital appreciation through the "
                "construction of a diversified investment portfolio."),
        evidence=('Firm\'s own website self-identifies as a single-family office: "manages the '
                  'philanthropic assets of Michael R. Bloomberg" — a dedicated office serving '
                  "one named individual. Discovered via a non-SEC curated-reference lens; "
                  "classification and firm identity verified against the firm's own website."),
        note=BASE_NOTE,
    ),
]


def fo_id(name: str) -> str:
    key = "name:" + re.sub(r"[^a-z0-9]+", " ", name.lower()).strip() + "|geo:?"
    return "fo_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


def build(d) -> FamilyOfficeRecord:
    def p(conf):
        return Provenance(source_class=SITE,
                          method="firm website (Firecrawl scrape + verification)",
                          checked_at=AS_OF, source_url=d["website"], confidence=conf)

    prov = {"name": p(Confidence.MEDIUM), "website": p(Confidence.HIGH),
            "description": p(Confidence.MEDIUM), "investment_thesis": p(Confidence.MEDIUM),
            "hq_country": p(Confidence.MEDIUM), "fo_type_evidence": p(Confidence.MEDIUM)}
    rec = FamilyOfficeRecord(
        fo_id=fo_id(d["name"]), name=d["name"], fo_type=FOType.SFO,
        fo_type_evidence=d["evidence"], fo_type_confidence=Confidence.MEDIUM,
        description=d["desc"], investment_thesis=d["thesis"], website=d["website"],
        hq_city=d["city"], hq_state=d["state"], hq_country=d["country"],
        discovery_source=DIR,
        verification_sources=[SourceRef(source_class=SITE,
                                        verifies="single-family-office status, firm identity",
                                        accessed_at=AS_OF, url=d["website"])],
        reviewer_notes=d["note"], record_confidence=Confidence.MEDIUM, data_as_of=AS_OF,
        could_not_verify=["estimated_aum", "corporate_linkedin", "principal_name",
                          "principal_title", "principal_linkedin", "principal_email",
                          "principal_phone", "hq_phone"],
        provenance=prov)
    return rec


def main():
    records = load_records_from_store()
    audit = [AuditEntry.model_validate(a)
             for a in json.loads(Path("data/final/audit.json").read_text(encoding="utf-8"))]
    have_ids = {r.fo_id for r in records}
    have_dom = {(r.website or "").split("//")[-1].split("/")[0].replace("www.", "").lower()
                for r in records if r.website}

    added = []
    for d in NEW:
        dom = d["website"].split("//")[-1].split("/")[0].replace("www.", "").lower()
        rid = fo_id(d["name"])
        if rid in have_ids or dom in have_dom:
            print("  skip (already present):", d["name"])
            continue
        rec = build(d)
        assert rec.qualifies()
        assert not rec.provenance_violations(), rec.provenance_violations()
        assert not [f for f in rec.could_not_verify if getattr(rec, f, None)]
        records.append(rec)
        added.append(rec.name)

    Path("data/final/records.json").write_text(
        json.dumps([r.model_dump(mode="json") for r in records], indent=1, ensure_ascii=False),
        encoding="utf-8")
    res = export_dataset(records, audit=audit, out_dir="data/final")
    precompute_and_save(records)

    from collections import Counter
    print("===== SFO EXPANSION =====")
    print(f"  added: {added}")
    print(f"  records now: {res['records']} | provenance rows: {res['provenance_rows']}")
    print("  type:", dict(Counter(r.fo_type.value for r in records)))
    print("  confidence:", dict(Counter(r.record_confidence.value for r in records)))


if __name__ == "__main__":
    main()
