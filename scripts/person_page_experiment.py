"""
Sample-first experiment: can page-driven person discovery (no seed name)
independently find real decision-makers on non-SEC family-office sites?

Selection: 12 gold-set firms (tests/goldset/raw_source.jsonl) whose fixture
data suggested a real team page might exist (selection heuristic only — the
fixture's names/emails are never passed into discovery itself). Domain is
resolved LIVE via the real production path (domain_search / resolve_domain),
not read from the fixture. No name is given to the extractor.

Never touches data/final.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SAMPLE = [
    "HVC Management", "Berkocorp", "Tacita Capital", "Buzbuzian Capital",
    "Genico Family Office", "Cervin Family Office and Advisors",
    "One Family Office", "Intevo Family Office", "C13 Investimentos",
    "Faerie Management", "Islandbridge", "Chi Fan Group",
]


def run() -> dict:
    from fointel.enrichment.website import WebsiteEnricher
    from fointel.enrichment.person_page_discovery import discover_people

    web = WebsiteEnricher()
    results = []
    for name in SAMPLE:
        # LIVE domain resolution, same production path — not read from the fixture.
        domain = web.resolve_domain(name)
        row = {"firm": name, "domain": domain, "pages_checked": [],
              "people": [], "verified": 0, "possible": 0, "failure": None}
        if not domain:
            row["failure"] = "no domain resolved/verified"
            results.append(row)
            continue

        people, pages = discover_people(web, domain)
        row["pages_checked"] = pages
        if not pages:
            row["failure"] = "no team page reachable"
        elif not people:
            row["failure"] = "person extraction failure (page fetched, no candidate found)"
        row["people"] = [
            {"name": p.name, "title": p.title, "email": p.email,
             "linkedin": p.linkedin, "verdict": p.verdict, "source_url": p.source_url}
            for p in people
        ]
        row["verified"] = sum(1 for p in people if p.verdict == "verified_decision_maker")
        row["possible"] = sum(1 for p in people if p.verdict == "possible_decision_maker")
        results.append(row)

    n = len(results)
    n_team_page = sum(1 for r in results if r["pages_checked"])
    n_people = sum(len(r["people"]) for r in results)
    n_verified = sum(r["verified"] for r in results)
    n_possible = sum(r["possible"] for r in results)
    n_email = sum(1 for r in results for p in r["people"] if p["email"])
    n_linkedin = sum(1 for r in results for p in r["people"] if p["linkedin"])

    return {
        "sample_size": n, "team_pages_found": n_team_page,
        "people_extracted": n_people, "verified_decision_makers": n_verified,
        "possible_decision_makers": n_possible,
        "named_person_emails": n_email, "named_person_linkedin": n_linkedin,
        "rows": results,
    }


if __name__ == "__main__":
    res = run()
    out = ROOT / "docs" / "evidence" / "person-page-discovery-experiment.json"
    out.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(f"Family Offices tested       = {res['sample_size']}")
    print(f"Team pages found            = {res['team_pages_found']}")
    print(f"People extracted            = {res['people_extracted']}")
    print(f"Verified decision-makers    = {res['verified_decision_makers']}")
    print(f"Possible decision-makers    = {res['possible_decision_makers']}")
    print(f"Named-person emails         = {res['named_person_emails']}")
    print(f"Current LinkedIn URLs       = {res['named_person_linkedin']}")
    print()
    for r in res["rows"]:
        print(f"{r['firm']:<38} domain={r['domain']} pages={len(r['pages_checked'])} "
              f"people={len(r['people'])} verified={r['verified']} fail={r['failure']}")
    print(f"\nwrote {out.relative_to(ROOT)}")
