"""
SFO expansion batch 2, phase 2 — append the three website-verified single-family offices
(from scripts/verify_sfo_batch2.py, human-reviewed) to the canonical store.

Review outcomes recorded here: Cherng Family Trust and Blue Haven Initiative passed the
automated gate; Artemis was accepted ON HUMAN REVIEW with the site's verbatim opening
line ("Artemis is the investment company of the Pinault family") after the automated
judge — running on a fallback model — missed it; the construction is identical to the
accepted Korys evidence. Dentressangle was REJECTED because its site names no family
except via the brand (inference is not evidence). Geography is left blank where the
site does not state it. Idempotent.
    py -3.12 scripts/add_sfo_batch2.py
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

BASE_NOTE = ("Discovered via the curated/notable-reference lens; classification and firm "
             "identity verified against the firm's own authoritative website (single "
             "verification source). AUM and individual contact details are not available "
             "from free authoritative sources and are left could_not_verify.")

NEW = [
    dict(
        name="Cherng Family Trust",
        website="https://www.cherngfamilytrust.com/",
        city=None, state=None, country=None,
        desc=("Multi-generational family office and investment firm of Andrew and Peggy "
              "Cherng, founders of Panda Restaurant Group."),
        thesis=None,
        evidence=('Firm\'s own website self-identifies as a single-family office: "Cherng '
                  'Family Trust is the multi-generational family office and investment firm of '
                  'Andrew and Peggy Cherng (the founders of Panda Express / Panda Restaurant '
                  'Group) and their family." Discovered via a curated-reference lens; verified '
                  "against the firm's own website."),
        note=BASE_NOTE,
    ),
    dict(
        name="Blue Haven Initiative",
        website="https://www.bluehaveninitiative.com/",
        city=None, state=None, country=None,
        desc=("Family office dedicated to putting wealth to work for competitive returns and "
              "meaningful impact."),
        thesis=("We believe that solving the world's biggest social and environmental issues "
                "requires creative long-term investors who prioritize partnership, patience "
                "and continuous learning."),
        evidence=('Firm\'s own website self-identifies as a family office serving one family: '
                  '"We are a family office investing with high standards, our team is dedicated '
                  'to using a full complement of capital tools available to leverage our '
                  'flexibility and multigenerational time horizon." (founders named on the '
                  "site). Discovered via a curated-reference lens; verified against the firm's "
                  "own website."),
        note=BASE_NOTE,
    ),
    dict(
        name="Artémis",
        website="https://www.groupeartemis.com/",
        city=None, state=None, country="France",
        desc=("Investment company of the Pinault family, founded in 1992 by François Pinault; "
              "carries out long-term investments in companies with strong growth potential."),
        thesis=("Long-term investments in companies with strong growth potential."),
        evidence=('Firm\'s own website self-identifies as a single-family office: "Artémis is '
                  'the investment company of the Pinault family. Founded in 1992 by François '
                  'Pinault, it carries out long term investments in companies with strong '
                  'growth potential." Discovered via a curated-reference lens; verified against '
                  "the firm's own website."),
        note=BASE_NOTE + " Accepted on human review: the automated judge (on a fallback model) "
             "missed the site's verbatim opening line, whose construction is identical to the "
             "accepted Korys evidence ('the ... investment company of the <family> family'); "
             "the overrule and its basis are recorded here for auditability. The site states "
             "the firm is French (groupe Artémis); city is not stated and is left blank.",
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
            "description": p(Confidence.MEDIUM), "fo_type_evidence": p(Confidence.MEDIUM)}
    if d["thesis"]:
        prov["investment_thesis"] = p(Confidence.MEDIUM)
    if d["country"]:
        prov["hq_country"] = p(Confidence.MEDIUM)
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
        if fo_id(d["name"]) in have_ids or dom in have_dom:
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
    print("===== SFO EXPANSION, BATCH 2 =====")
    print(f"  added: {added}")
    print(f"  records now: {res['records']}")
    print("  type:", dict(Counter(r.fo_type.value for r in records)))
    print("  confidence:", dict(Counter(r.record_confidence.value for r in records)))


if __name__ == "__main__":
    main()
