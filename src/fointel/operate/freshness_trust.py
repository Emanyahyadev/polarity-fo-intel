"""
Cross-run staleness/trust comparison — the piece FreshnessAgent was missing.

Real staleness detection compares the CURRENT release-authorized dataset
against a snapshot persisted by the PREVIOUS cycle, field by field, on the
trust-bearing columns. A record flips to "stale" only when something
concrete changed between two genuinely separate cycles: a classification
flipped, a confidence level dropped, a contact field disappeared or changed,
or AUM changed. This is evidence-based (a real diff), never a clock-based
day-count — the day-count staleness bar already lives separately in
`src/fointel/agent/evidence.py` for the customer-facing agent and is not
what this module does.

The first-ever run has no prior snapshot: it establishes the baseline and
reports zero stale records (honestly — there is nothing to compare against
yet), never a fabricated flag.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_SNAPSHOT_PATH = "data/freshness/prior_snapshot.json"

# The trust-bearing fields a customer-visible claim depends on. A change here
# is exactly the kind of thing that should reduce trust in a held record.
TRUST_FIELDS = [
    "fo_type", "fo_type_evidence", "fo_type_confidence", "record_confidence",
    "principal_name", "principal_email", "principal_email_status",
    "principal_linkedin", "principal_phone", "firm_contact_email",
    "estimated_aum",
]


def _field_value(rec: dict, field: str) -> Any:
    v = rec.get(field)
    if isinstance(v, list):
        return sorted(str(x) for x in v)
    return v


def build_snapshot(records: list[dict]) -> dict[str, dict]:
    """fo_id -> {field: value} for every trust-bearing field, plus a
    verification-source count (a corroboration drop is itself a trust signal)."""
    snap = {}
    for r in records:
        fo_id = r.get("fo_id")
        if not fo_id:
            continue
        entry = {f: _field_value(r, f) for f in TRUST_FIELDS}
        vsrc = r.get("verification_sources") or []
        entry["_n_verification_sources"] = len(vsrc)
        snap[fo_id] = entry
    return snap


def load_snapshot(path: str | Path = DEFAULT_SNAPSHOT_PATH) -> dict[str, dict] | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_snapshot(snapshot: dict[str, dict], path: str | Path = DEFAULT_SNAPSHOT_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snapshot, indent=2, sort_keys=True, default=str), encoding="utf-8")


def compare(prior: dict[str, dict], current: dict[str, dict]) -> list[dict]:
    """Records present in BOTH snapshots whose trust-bearing fields diverged.
    A record only in `current` (newly released) is not staleness — it has no
    earlier-cycle state to contradict. A record only in `prior` (no longer
    released) is not reported here either; that is a release-layer event."""
    events = []
    for fo_id, cur in current.items():
        prev = prior.get(fo_id)
        if prev is None:
            continue
        changed = []
        for field in TRUST_FIELDS + ["_n_verification_sources"]:
            if prev.get(field) != cur.get(field):
                changed.append({"field": field, "was": prev.get(field), "now": cur.get(field)})
        if changed:
            if any(c["field"] == "_n_verification_sources" and
                   (c["now"] or 0) < (c["was"] or 0) for c in changed):
                reason = "a source that previously corroborated this record no longer does (verification-source count dropped)"
            elif any(c["field"] in ("fo_type", "fo_type_evidence") for c in changed):
                reason = "classification/evidence changed on re-verification between cycles"
            elif any(c["field"] == "record_confidence" for c in changed):
                reason = "record confidence changed on re-verification between cycles"
            elif any(c["field"] in ("principal_email", "principal_linkedin", "principal_phone",
                                    "firm_contact_email") for c in changed):
                reason = "a contact field changed or disappeared between cycles"
            else:
                reason = "a trust-bearing field changed on re-verification between cycles"
            events.append({"fo_id": fo_id, "reason": reason, "changed_fields": changed})
    return events


def run_cross_cycle_check(records: list[dict],
                          path: str | Path = DEFAULT_SNAPSHOT_PATH) -> dict:
    """Called once per operating cycle. Returns {stale: [...], baseline: bool}.
    Always persists the current snapshot as the new prior for the next cycle —
    this is what makes the check genuinely cross-run rather than in-session."""
    current = build_snapshot(records)
    prior = load_snapshot(path)
    if prior is None:
        save_snapshot(current, path)
        return {"stale": [], "baseline": True,
               "note": "no prior cycle snapshot found; this cycle establishes the baseline"}
    stale = compare(prior, current)
    save_snapshot(current, path)
    return {"stale": stale, "baseline": False,
           "note": f"compared against the snapshot from the previous cycle ({len(prior)} records)"}
