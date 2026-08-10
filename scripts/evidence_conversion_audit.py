"""Objective 1 — classify WHY rejected candidates fail, per stage, with real fetches.

Runs currently-unreleased pool candidates through the real enrichment path and
records what happened at each stage, so "no affirmative family-office evidence"
is decomposed into engineering failures vs genuine non-family-offices.

Categories (as specified):
  A genuinely not a family office (classifier gave a substantive non-FO reason)
  B family office but no domain available anywhere
  C domain resolution never ATTEMPTED (gated off) or attempted and failed
  D website fetch failed
  E website fetched but parser found no FO language
  F authoritative evidence likely exists elsewhere but pipeline never searched it
  G insufficient evidence genuinely
  H other

    python scripts/evidence_conversion_audit.py [N]
"""

from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

NON_FO_REASONS = ("pension", "benefit", "trustee", "membership", "association",
                  "network", "broker", "public compan", "fund", "bank")


def load_unreleased(limit: int) -> list:
    from fointel.rag.load import load_records_from_store
    from fointel.schema import Candidate
    norm = lambda s: re.sub(r"[^a-z0-9]", "", (s or "").lower())
    released = {norm(r.name) for r in load_records_from_store()}
    conn = sqlite3.connect(ROOT / "data" / "fointel.db")
    out = []
    for (payload,) in conn.execute("SELECT payload FROM candidates"):
        d = json.loads(payload)
        if norm(d.get("name")) in released:
            continue
        try:
            out.append(Candidate.model_validate(d))
        except Exception:
            continue
        if len(out) >= limit:
            break
    return out


def audit(n: int = 30) -> dict:
    from fointel.assemble import enrich_candidate
    from fointel.enrichment.adv import AdvEnricher
    from fointel.enrichment.iapd import IapdEnricher
    from fointel.enrichment.sec import SecEnricher
    from fointel.enrichment.thirteenf import ThirteenFEnricher
    from fointel.enrichment.website import WebsiteEnricher
    from fointel.enrichment.person_contact import PersonContactEnricher

    sec, web, iapd = SecEnricher(), WebsiteEnricher(), IapdEnricher()
    f13, adv, person = ThirteenFEnricher(), AdvEnricher(), PersonContactEnricher()

    cands = load_unreleased(n)
    cats: Counter = Counter()
    rows = []
    for cand in cands:
        name = cand.name
        name_has_fo = "family office" in name.lower()
        e = enrich_candidate(cand, sec, web, iapd, f13, adv, person)
        cls = e.classification
        reason = (cls.reject_reason or "").lower()
        wf = e.website_facts
        website = getattr(e, "website", None) or (wf.url if wf else None)

        if cls.qualifies:
            cat = "QUALIFIED"
        elif any(k in reason for k in NON_FO_REASONS):
            cat = "A genuinely not a family office"
        elif wf is not None and wf.resolved and not wf.fo_language:
            cat = "E website fetched, parser found no FO language"
        elif wf is not None and not wf.resolved:
            cat = "D website fetch failed"
        elif website and wf is None:
            cat = "D website fetch failed"
        elif not website and not name_has_fo:
            # domain resolution is gated behind a name/IAPD heuristic — never tried
            cat = "C domain resolution NEVER ATTEMPTED (name heuristic gate)"
        elif not website and name_has_fo:
            cat = "B likely FO but domain resolution attempted and failed"
        else:
            cat = "H other"

        cats[cat] += 1
        rows.append({"name": name, "source": cand.source_class.value,
                     "name_has_fo": name_has_fo, "website": website,
                     "site_resolved": bool(wf and wf.resolved),
                     "fo_language": bool(wf and wf.fo_language),
                     "qualifies": cls.qualifies,
                     "reject_reason": cls.reject_reason, "category": cat})
    return {"n": len(cands), "categories": dict(cats.most_common()), "rows": rows}


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 30
    res = audit(n)
    out = ROOT / "docs" / "evidence" / "evidence-conversion-audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(f"\n=== EVIDENCE CONVERSION AUDIT (n={res['n']}) ===")
    for cat, c in res["categories"].items():
        print(f"  {c:>3}  ({100*c/res['n']:>5.1f}%)  {cat}")
    print(f"\nwrote {out.relative_to(ROOT)}")
