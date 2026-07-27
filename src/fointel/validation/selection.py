"""
Final-dataset selection policy — enforces source diversity in the SHIPPED file.

The anti-"copy at scale" rule applies to what we deliver, not to the raw pool.
This selects the final N from gate-approved records so that no single **discovery**
source exceeds a cap (default 40% of N). If there are not enough diverse qualifying
records to fill N under the cap, the cap is relaxed to reach N — but only with an
explicit, logged justification (never silently). Within each source, higher-quality
records are preferred (confidence, then actionable contact, then dated signals, then
SFO). See gate-review A10 / DecisionLog D18.
"""

from __future__ import annotations

from collections import defaultdict

from ..observability import get_logger
from ..schema import Confidence, FamilyOfficeRecord, FOType

log = get_logger("release")

_CONF_RANK = {Confidence.HIGH: 3, Confidence.MEDIUM: 2, Confidence.LOW: 1}


def _quality(rec: FamilyOfficeRecord) -> tuple:
    actionable = 1 if (rec.principal_email or rec.principal_phone or rec.principal_linkedin) else 0
    has_signals = 1 if rec.signals else 0
    type_pref = {FOType.SFO: 2, FOType.MFO: 1}.get(rec.fo_type, 0)
    return (_CONF_RANK[rec.record_confidence], actionable, has_signals, type_pref)


def select_final(records: list[FamilyOfficeRecord], target: int = 50,
                 max_share: float = 0.4) -> tuple[list[FamilyOfficeRecord], dict]:
    """Select up to `target` gate-approved records, balanced across discovery sources."""
    cap = max(1, int(max_share * target))
    by_source: dict[str, list[FamilyOfficeRecord]] = defaultdict(list)
    for rec in records:
        by_source[rec.discovery_source.value].append(rec)
    for src in by_source:
        by_source[src].sort(key=_quality, reverse=True)

    pointers = {src: 0 for src in by_source}
    counts: dict[str, int] = defaultdict(int)
    selected: list[FamilyOfficeRecord] = []

    def take(src: str):
        i = pointers[src]
        if i < len(by_source[src]):
            pointers[src] = i + 1
            return by_source[src][i]
        return None

    # Phase 1 — round-robin under the per-source cap
    while len(selected) < target:
        took_any = False
        for src in list(by_source):
            if counts[src] >= cap:
                continue
            rec = take(src)
            if rec is None:
                continue
            selected.append(rec)
            counts[src] += 1
            took_any = True
            if len(selected) >= target:
                break
        if not took_any:
            break

    # Phase 2 — relax the cap only if short, and only with a logged justification
    relaxed, justification = False, ""
    if len(selected) < target:
        leftovers = [rec for src in by_source for rec in by_source[src][pointers[src]:]]
        leftovers.sort(key=_quality, reverse=True)
        for rec in leftovers[: target - len(selected)]:
            selected.append(rec)
            counts[rec.discovery_source.value] += 1
        if leftovers:
            relaxed = True
            over = {s: c for s, c in counts.items() if c > cap}
            justification = (f"insufficient diverse qualifying records to fill {target} under a "
                             f"{cap}-per-source cap; cap relaxed for {list(over)} to reach target")
            log.warning("selection cap relaxed", extra={
                "event": "selection_relaxed", "over": over, "target": target})

    report = {
        "target": target,
        "cap_per_source": cap,
        "selected": len(selected),
        "source_counts": dict(counts),
        "cap_relaxed": relaxed,
        "justification": justification,
    }
    log.info("final selection", extra={"event": "selection", "selected": len(selected),
                                       "source_counts": dict(counts), "cap_relaxed": relaxed})
    return selected, report
