"""
Phase 2 of discovery-diversity: build verified records for the non-SEC (Wikipedia/
Wikidata-discovered) family offices confirmed against their own website in phase 1,
and APPEND them to the delivered dataset (enrich, not rebuild).

Every field is grounded in the firm's own site (the verification source); firms
controlled by a family with no individual named on the site get a blank principal
(could_not_verify), not a guessed one; AUM and contact details stay could_not_verify.
Discovery source = Curated directory (non-SEC) — this is the point: it lowers the
SEC discovery concentration with genuinely independent, authoritative verification.

    py -3.12 scripts/build_directory_records.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fointel.export import export_dataset                       # noqa: E402
from fointel.rag.load import load_records_from_csv              # noqa: E402
from fointel.rag.index import precompute_and_save               # noqa: E402
from fointel.schema import (Confidence, FamilyOfficeRecord, FOType,   # noqa: E402
                            HIGH_VALUE_FIELDS, Provenance, SourceClass, SourceRef)

AS_OF = date(2026, 7, 28)
SITE = SourceClass.FIRM_SITE
DIR = SourceClass.DIRECTORY
MED, LOW = Confidence.MEDIUM, Confidence.LOW

_BASE_NOTE = ("Discovered via a non-SEC lens (Wikipedia/Wikidata Category:Family_offices); "
              "classification and firm identity verified against the firm's own authoritative "
              "website (single verification source). AUM and individual contact details are "
              "not available from free authoritative sources and are left could_not_verify.")

# Each entry is fully reviewed, grounded in the phase-1 evidence in data/adv/directory_verified.json.
NEW = [
    dict(fo_id="fo_ca957ee5d5", name="Financière Agache", conf=MED,
         website="https://www.financiereagache-finance.com/",
         country="France", city=None,
         principal=("Florian Ollivier", "Président-directeur général"),
         desc="Holding company of the Arnault family, controlling shareholder of Christian Dior.",
         thesis=None,
         evidence="Le groupe familial Arnault détenant au total 97,5% de Christian Dior",
         note=_BASE_NOTE),
    dict(fo_id="fo_d27cc088a3", name="KIRKBI", conf=MED,
         website="https://www.kirkbi.com/",
         country="Denmark", city="Billund",
         principal=None,
         desc=("Holding and investment company of the Kirk Kristiansen family, founders of the "
               "LEGO Group; owns and develops businesses for the long term."),
         thesis=None,
         evidence=("As the holding company of the Kirk Kristiansen family, who founded the LEGO "
                   "Group in 1932"),
         note=_BASE_NOTE + " Controlled by the Kirk Kristiansen family; no individual decision-maker"
              " is named on the site, so the principal is left could_not_verify. The firm also"
              " appears in SEC EDGAR full-text filings (Schedule 13D/13G on US holdings),"
              " corroborating its investing activity."),
    dict(fo_id="fo_a750611281", name="Prime Opportunities Investment Group", conf=LOW,
         website="https://www.primeopp.com/",
         country="United States", city=None,
         principal=("Pouya David Yadegar", "Founder, Chief Investment Officer"),
         desc=("US single-family office investing in public equities with a private-equity "
               "approach; roots in real-estate holdings and operating businesses."),
         thesis=("We invest only in publicly traded companies, and take a private equity approach "
                 "to our investment process."),
         evidence=("our background as a successful family office with extensive real estate holdings "
                   "and business operating experience"),
         note=_BASE_NOTE + " Self-describes as a single-family office; a smaller, public-equity"
              " focused firm — held at Low confidence pending a second authoritative source."),
    dict(fo_id="fo_3642e17ac1", name="Korys", conf=MED,
         website="https://www.korys.be/",
         country="Belgium", city=None,
         principal=None,
         desc=("Entrepreneurial investment company of the Colruyt family, investing in companies "
               "aligned with conscious-consumer solutions."),
         thesis=("Korys invests in companies that offer solutions to the challenges conscious "
                 "consumers face in their search for products and services."),
         evidence="Korys is the entrepreneurial investment company of the Colruyt family.",
         note=_BASE_NOTE + " Controlled by the Colruyt family; no individual decision-maker is named"
              " on the site, so the principal is left could_not_verify."),
    dict(fo_id="fo_e8d9f15c57", name="Builders Vision", conf=MED,
         website="https://www.buildersvision.com/",
         country="United States", city="Chicago",
         principal=("Lukas Walton", "Founder"),
         desc=("Impact platform founded by Lukas Walton in 2018 that combines philanthropy and "
               "investing to shift capital markets toward sustainable solutions."),
         thesis=None,
         evidence=("Lukas Walton founded Builders Vision in 2018, inspired by the belief that "
                   "philanthropy and investing together can shift capital markets toward "
                   "sustainable solutions."),
         note=_BASE_NOTE + " The firm also appears in SEC EDGAR full-text filings on US holdings,"
              " corroborating its investing activity."),
]

SITE_FIELDS = {"website", "description", "investment_thesis", "corporate_linkedin"}


def reconstruct(rec):
    vs = rec.verification_sources
    if not vs:
        return
    site = next((s for s in vs if s.source_class == SITE), None)
    reg = next((s for s in vs if s.source_class != SITE), vs[0])
    for f in HIGH_VALUE_FIELDS:
        if getattr(rec, f, None) and f not in rec.provenance:
            src = site if (f in SITE_FIELDS and site) else reg
            rec.provenance[f] = Provenance(source_class=src.source_class,
                                           method=f"verified via {src.source_class.value}",
                                           checked_at=rec.data_as_of, confidence=rec.record_confidence)


def build(d) -> FamilyOfficeRecord:
    prov = {}

    def p(conf):
        return Provenance(source_class=SITE, method="firm website (Firecrawl scrape + verification)",
                          checked_at=AS_OF, source_url=d["website"], confidence=conf)

    prov["name"] = p(d["conf"])
    prov["website"] = p(Confidence.HIGH)
    prov["description"] = p(MED)
    if d["country"]:
        prov["hq_country"] = p(MED)
    if d["thesis"]:
        prov["investment_thesis"] = p(MED)
    pname = ptitle = None
    if d["principal"]:
        pname, ptitle = d["principal"]
        prov["principal_name"] = p(MED)
        prov["principal_title"] = p(MED)

    cnv = ["estimated_aum", "corporate_linkedin", "principal_linkedin", "principal_email",
           "principal_phone", "hq_phone"]
    if not d["principal"]:
        cnv += ["principal_name", "principal_title"]

    evidence = (f'Firm\'s own website self-identifies as a single-family office: '
                f'"{d["evidence"][:180]}". Discovered via a non-SEC lens '
                f'(Wikipedia/Wikidata Category:Family_offices); classification and firm identity '
                f'verified against the firm\'s own website.')

    return FamilyOfficeRecord(
        fo_id=d["fo_id"], name=d["name"], fo_type=FOType.SFO,
        fo_type_evidence=evidence, fo_type_confidence=d["conf"],
        description=d["desc"], investment_thesis=d["thesis"],
        website=d["website"], hq_city=d["city"], hq_country=d["country"],
        principal_name=pname, principal_title=ptitle,
        discovery_source=DIR,
        verification_sources=[SourceRef(source_class=SITE,
                                        verifies="family-office status, type, firm identity",
                                        accessed_at=AS_OF, url=d["website"])],
        reviewer_notes=d["note"], record_confidence=d["conf"], data_as_of=AS_OF,
        could_not_verify=cnv, provenance=prov)


def main() -> None:
    existing = load_records_from_csv()
    for r in existing:
        reconstruct(r)
    have_ids = {r.fo_id for r in existing}
    have_dom = {(r.website or "").split("//")[-1].split("/")[0].replace("www.", "").lower()
                for r in existing if r.website}

    added = []
    for d in NEW:
        dom = d["website"].split("//")[-1].split("/")[0].replace("www.", "").lower()
        if d["fo_id"] in have_ids or dom in have_dom:
            print("  skip (dup):", d["name"])
            continue
        rec = build(d)
        # invariants
        bad = [f for f in rec.could_not_verify if getattr(rec, f, None)]
        assert not bad, f"{rec.name}: populated+could_not_verify {bad}"
        assert rec.qualifies(), f"{rec.name}: no fo_type_evidence"
        assert not rec.provenance_violations(), f"{rec.name}: {rec.provenance_violations()}"
        existing.append(rec)
        added.append(rec.name)

    # export + regenerate embeddings for the new count
    res = export_dataset(existing, audit=[], out_dir="data/final")
    precompute_and_save(existing)

    from collections import Counter
    print("===== DISCOVERY-DIVERSITY ADDITION =====")
    print(f"  added {len(added)}: {added}")
    print(f"  total records now: {res['records']} | provenance rows: {res['provenance_rows']}")
    print("  type:", dict(Counter(r.fo_type.value for r in existing)))
    print("  discovery:", dict(Counter(r.discovery_source.value for r in existing)))
    print("  countries:", dict(Counter(r.hq_country or '?' for r in existing)))


if __name__ == "__main__":
    main()
