"""Continuous collection — the 48-hour "harvest to target" mode.

The scheduled cycle is one window; continuous collection re-wakes the cycle over
and over (idempotently — the release agent merges into the canonical store) until
a target number of VERIFIED CONTACTS is reached or a time budget is exhausted.

A verified contact is a released record with at least one verification source
AND at least one reachable channel (published email, phone, LinkedIn, or the
firm's own website). Pure helpers here are unit-testable without network.
"""

from __future__ import annotations

import math
from typing import Any

# NOTE: this is a REACHABILITY channel list (any outreach path), not a named-person
# route list — firm_contact_email counts here (same as website) even though it is
# explicitly NOT a principal route (see schema.py). Do not use this list where the
# stricter "named individual reachable" claim is required (see validation/gates.py
# and validation/selection.py's `actionable`, which intentionally use only the
# principal_* fields).
CONTACT_CHANNELS = ("principal_email", "principal_phone", "firm_contact_email",
                    "corporate_linkedin", "principal_linkedin", "website")


def _has(record: Any, field: str) -> Any:
    if isinstance(record, dict):
        return record.get(field)
    return getattr(record, field, None)


def is_verified_contact(record: Any) -> bool:
    """A released record counts toward the target only when it is VERIFIED
    (independent verification source recorded) and REACHABLE (published email,
    phone, LinkedIn, or website — an outreach channel actually exists)."""
    if not _has(record, "verification_sources"):
        return False
    return any(_has(record, f) for f in CONTACT_CHANNELS)


def contact_count(records: list[Any]) -> int:
    return sum(1 for r in records if is_verified_contact(r))


def planned_cycles(budget_hours: float, interval_min: float,
                   target: int, current: int) -> int:
    """How many full cycles fit in the budget, minus one so the final sleep never
    pushes past the deadline (the run stops as soon as it is done either way).
    At least 1 when the target is not yet met; 0 when it already is."""
    if current >= target:
        return 0
    return max(1, int(math.floor((budget_hours * 60.0) / max(interval_min, 0.1))) - 1)