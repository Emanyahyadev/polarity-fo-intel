"""Funnel audit — exact counts and conversion rates at every acquisition stage.

Measures, never estimates. Reads the candidate pool (SQLite) and the released
store (records.json), evaluates every released record against the real
ReleaseGate, and classifies every gate failure by reason so the largest
rejection category is a number rather than a guess.

    python scripts/funnel_audit.py            # human-readable report
    python scripts/funnel_audit.py --json     # machine-readable
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DB = ROOT / "data" / "fointel.db"
GENERIC_LOCALPARTS = {"info", "contact", "hello", "office", "admin", "mail",
                      "invest", "connect", "enquiries", "enquiry", "team",
                      "reception", "manage", "noreply", "no-reply"}


def _pool_counts() -> dict:
    if not DB.exists():
        return {"total": 0, "by_source": {}}
    conn = sqlite3.connect(DB)
    try:
        total = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        by_src = dict(conn.execute(
            "SELECT source_class, COUNT(*) FROM candidates GROUP BY source_class").fetchall())
    except sqlite3.OperationalError:
        return {"total": 0, "by_source": {}}
    return {"total": total, "by_source": by_src}


def _is_named_person_email(rec) -> bool:
    """A qualifying professional email: present, tied to a named person, and not
    a generic/shared mailbox. Mirrors the Differentiator floor exactly."""
    email = (rec.principal_email or "").strip()
    if not email or "@" not in email:
        return False
    if not (rec.principal_name or "").strip():
        return False
    return email.split("@", 1)[0].strip().lower() not in GENERIC_LOCALPARTS


def audit() -> dict:
    from fointel.rag.load import load_records_from_store
    from fointel.validation.gates import ReleaseGate

    records = load_records_from_store()
    gate = ReleaseGate()
    pool = _pool_counts()

    released = len(records)
    unique_ids = len({r.fo_id for r in records})

    passing, failing = [], []
    fail_reasons: Counter = Counter()
    for r in records:
        out = gate.evaluate(r)
        if out.passed:
            passing.append(r)
        else:
            failing.append(r)
            for chk in out.checks:
                if not chk.passed:
                    fail_reasons[f"{chk.name}: {chk.detail}"] += 1

    has_location = sum(1 for r in records if r.hq_country or r.hq_state or r.hq_city)
    has_principal = sum(1 for r in records if (r.principal_name or "").strip())
    has_named_email = sum(1 for r in records if _is_named_person_email(r))
    has_any_named_route = sum(
        1 for r in records
        if _is_named_person_email(r) or r.principal_linkedin or r.principal_phone)
    has_firm_inbox = sum(1 for r in records if (r.firm_contact_email or "").strip())
    enriched_beyond_seed = sum(
        1 for r in records
        if any(v.source_class != r.discovery_source for v in r.verification_sources))
    two_plus_sources = sum(1 for r in records if len(r.verification_sources) >= 2)

    def pct(n: int, d: int) -> float:
        return round(100.0 * n / d, 1) if d else 0.0

    return {
        "pool": pool,
        "released_rows": released,
        "released_unique": unique_ids,
        "gate_passing": len(passing),
        "gate_failing": len(failing),
        "gate_failure_reasons": dict(fail_reasons.most_common()),
        "has_location": has_location,
        "has_principal_name": has_principal,
        "named_person_email": has_named_email,
        "any_named_person_route": has_any_named_route,
        "firm_inbox_only_field": has_firm_inbox,
        "enriched_beyond_seed": enriched_beyond_seed,
        "two_plus_verification_sources": two_plus_sources,
        "conversion": {
            "pool_to_released_pct": pct(released, pool["total"]),
            "released_to_gate_passing_pct": pct(len(passing), released),
            "released_to_location_pct": pct(has_location, released),
            "released_to_principal_pct": pct(has_principal, released),
            "principal_to_named_email_pct": pct(has_named_email, has_principal),
            "released_to_named_email_pct": pct(has_named_email, released),
        },
        "remaining": {
            "to_500_qualifying": max(0, 500 - len(passing)),
            "to_200_named_emails": max(0, 200 - has_named_email),
        },
    }


def main() -> int:
    a = audit()
    if "--json" in sys.argv:
        print(json.dumps(a, indent=2))
        return 0

    p, c, rem = a["pool"], a["conversion"], a["remaining"]
    print("=" * 62)
    print("ACQUISITION FUNNEL AUDIT")
    print("=" * 62)
    print(f"CANDIDATE POOL                {p['total']:>6}")
    for src, n in sorted(p["by_source"].items(), key=lambda kv: -kv[1]):
        print(f"    {src[:46]:<46} {n:>5}")
    print(f"RELEASED ROWS                 {a['released_rows']:>6}")
    print(f"RELEASED UNIQUE (by fo_id)    {a['released_unique']:>6}")
    print(f"GATE-PASSING (qualifying)     {a['gate_passing']:>6}")
    print(f"GATE-FAILING (shipped anyway) {a['gate_failing']:>6}")
    print()
    print("--- per-field coverage of released records ---")
    print(f"  location present            {a['has_location']:>6}")
    print(f"  principal named             {a['has_principal_name']:>6}")
    print(f"  NAMED-PERSON EMAIL          {a['named_person_email']:>6}")
    print(f"  any named-person route      {a['any_named_person_route']:>6}")
    print(f"  enriched beyond seed source {a['enriched_beyond_seed']:>6}")
    print(f"  2+ verification sources     {a['two_plus_verification_sources']:>6}")
    print()
    print("--- conversion ---")
    for k, v in c.items():
        print(f"  {k:<34} {v:>6}%")
    print()
    if a["gate_failure_reasons"]:
        print("--- gate failure reasons (largest first) ---")
        for reason, n in a["gate_failure_reasons"].items():
            print(f"  {n:>4}x  {reason[:80]}")
        print()
    print("--- remaining to target ---")
    print(f"  to 500 qualifying records   {rem['to_500_qualifying']:>6}")
    print(f"  to 200 named-person emails  {rem['to_200_named_emails']:>6}")
    print("=" * 62)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
