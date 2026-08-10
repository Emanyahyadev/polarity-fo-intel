"""
Gold-set blind rediscovery benchmark. See tests/goldset/README.md for the full
disclosure of what this is, why it exists, and the rules it enforces.

For each gold-set organization, the autonomous discovery/enrichment/
classification path is run from the NAME ONLY (never the fixture's website,
email, or phone). The fixture's own fields are read only afterward, to score
the run — never fed into it.

Never writes to data/final. Never affects production counts.
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

FIXTURE = ROOT / "tests" / "goldset" / "raw_source.jsonl"
GENERIC_LOCALPARTS = {"info", "contact", "hello", "office", "admin", "mail",
                      "invest", "connect", "enquiries", "enquiry", "welcome",
                      "reception", "general", "hr", "media", "team", "support"}


def _is_named_person_email(email: str) -> bool:
    """A qualifying named-person email: not a generic/shared mailbox local-part.
    (This does not by itself prove ownership by the specific named individual —
    that identity binding is PersonContactEnricher's job upstream; this is only
    the generic-mailbox exclusion the Differentiator requires.)"""
    if not email or "@" not in email:
        return False
    local = email.split("@", 1)[0].strip().lower()
    return local not in GENERIC_LOCALPARTS


def _load_fixture(n: int | None) -> list[dict]:
    rows = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[:n] if n else rows


def run(n: int | None) -> dict:
    from fointel.schema import Candidate, SourceClass
    from fointel.assemble import enrich_candidate
    from fointel.enrichment.adv import AdvEnricher
    from fointel.enrichment.iapd import IapdEnricher
    from fointel.enrichment.sec import SecEnricher
    from fointel.enrichment.thirteenf import ThirteenFEnricher
    from fointel.enrichment.website import WebsiteEnricher
    from fointel.enrichment.person_contact import PersonContactEnricher
    import fointel.enrichment.domain_search as domain_search_mod

    sec, web, iapd = SecEnricher(), WebsiteEnricher(), IapdEnricher()
    f13, adv, person = ThirteenFEnricher(), AdvEnricher(), PersonContactEnricher()

    gold = _load_fixture(n)
    results = []
    provider_hits: Counter = Counter()
    fail_modes: Counter = Counter()

    orig_find = domain_search_mod.find_official_domain

    for g in gold:
        name = g["candidate_name"]
        # BLIND INPUT: name only. No website, email, phone, or address from the
        # fixture is passed into the candidate or any enricher.
        cand = Candidate(name=name, source_class=SourceClass.WEB,
                         source_url=None, discovered_at=date.today(),
                         dedup_key=re.sub(r"[^a-z0-9]", "", name.lower()))

        provider_used = {"name": None}
        def _wrapped(firm_name, _orig=orig_find, _p=provider_used):
            hit = _orig(firm_name)
            if hit:
                _p["name"] = hit.provider
            return hit
        domain_search_mod.find_official_domain = _wrapped

        try:
            e = enrich_candidate(cand, sec, web, iapd, f13, adv, person)
        finally:
            domain_search_mod.find_official_domain = orig_find

        wf = e.website_facts
        resolved_url = getattr(e, "website", None) or (wf.url if wf else None)
        qualifies = e.classification.qualifies
        pc = e.person_contact

        # Compare resolved domain host to the gold (fixture) host — comparison
        # only, never fed back into the run.
        def _host(u):
            m = re.search(r"https?://(?:www\.)?([^/?#]+)", (u or "").lower())
            return m.group(1) if m else ""
        domain_match = bool(resolved_url) and _host(resolved_url) == _host(g.get("website"))

        if provider_used["name"]:
            provider_hits[provider_used["name"]] += 1

        # Failure classification from the actual execution trace, not inference.
        if qualifies:
            mode = "QUALIFIED"
        elif not resolved_url and not provider_used["name"]:
            mode = "C provider coverage failure (no provider returned a domain)"
        elif resolved_url and not domain_match:
            mode = "D domain-resolution mismatch (resolved a different/no site)"
        elif wf is not None and wf.resolved and not wf.fo_language:
            mode = "F evidence extraction failure (site fetched, no FO language found)"
        elif not e.classification.qualifies and e.classification.reject_reason:
            mode = "J legitimate policy rejection: " + (e.classification.reject_reason or "")[:80]
        else:
            mode = "K genuine source/data unavailability"
        fail_modes[mode] += 1

        named_email = bool(pc and pc.found and pc.email and _is_named_person_email(pc.email))
        contact_route = named_email or bool(pc and pc.found and pc.linkedin)

        results.append({
            "gold_name": name, "gold_country": g.get("country"),
            "gold_possible_type": g.get("possible_type"),
            "autonomous_domain": resolved_url, "gold_domain": g.get("website"),
            "domain_match": domain_match, "provider": provider_used["name"],
            "evidence_found": bool(wf and wf.resolved and wf.fo_language),
            "qualified": qualifies, "fo_type": e.classification.fo_type if qualifies else None,
            "decision_maker_found": bool(pc and pc.found),
            "contact_route_found": contact_route,
            "named_person_email_found": named_email,
            "failure_mode": mode,
        })

    n_total = len(results)
    n_domain = sum(1 for r in results if r["domain_match"])
    n_evidence = sum(1 for r in results if r["evidence_found"])
    n_qualified = sum(1 for r in results if r["qualified"])
    n_dm = sum(1 for r in results if r["decision_maker_found"])
    n_contact = sum(1 for r in results if r["contact_route_found"])
    n_email = sum(1 for r in results if r["named_person_email_found"])

    def pct(a):
        return round(100.0 * a / n_total, 1) if n_total else 0.0

    return {
        "gold_set_size": n_total,
        "domain_resolved": n_domain, "evidence_verified": n_evidence,
        "qualified": n_qualified, "decision_maker_found": n_dm,
        "contact_route_found": n_contact, "named_person_email_found": n_email,
        "recall": {
            "domain_recall_pct": pct(n_domain), "evidence_recall_pct": pct(n_evidence),
            "qualification_recall_pct": pct(n_qualified),
            "contact_route_recall_pct": pct(n_contact),
            "named_person_email_recall_pct": pct(n_email),
        },
        "provider_contribution": dict(provider_hits),
        "failure_modes": dict(fail_modes.most_common()),
        "rows": results,
    }


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    res = run(n)
    out_dir = ROOT / "docs" / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = sys.argv[2] if len(sys.argv) > 2 else "BASELINE"
    out = out_dir / f"goldset-rediscovery-{tag}.json"
    out.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")

    print(f"\n=== GOLD-SET REDISCOVERY ({tag}), n={res['gold_set_size']} ===")
    for k, v in res["recall"].items():
        print(f"  {k:<32} {v:>6}%")
    print("\n--- provider contribution ---")
    for k, v in res["provider_contribution"].items():
        print(f"  {v:>3}  {k}")
    print("\n--- failure modes ---")
    for k, v in res["failure_modes"].items():
        print(f"  {v:>3}  {k}")
    print(f"\nwrote {out.relative_to(ROOT)}")
