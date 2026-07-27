"""
Candidate harvest: run every discovery source, resolve entities (evidence-based,
logged), persist the pool, and report the per-source distribution + cross-source
overlap + merge decisions.

The distribution report is the evidence that discovery is genuinely multi-source
(no single source dominates) — the assessment's load-bearing anti-"copy at scale"
check. A source that raises is logged and skipped, never allowed to fail silently.
De-duplication is delegated to EntityResolver so no distinct firm is ever silently
dropped and every merge/kept-distinct decision is recorded.
"""

from __future__ import annotations

from typing import Optional

from ..entity_resolution import EntityResolver, MergeDecision
from ..observability import get_logger
from ..store import Repository
from .base import DiscoverySource
from .directory import DirectorySource
from .irs_990pf import Irs990pfSource
from .news import NewsSource
from .sec_edgar import SecEdgarSource

log = get_logger("discovery")


def default_sources() -> list[DiscoverySource]:
    return [SecEdgarSource(), Irs990pfSource(), DirectorySource(), NewsSource()]


def harvest(repo: Repository, per_source_limit: int,
            sources: Optional[list[DiscoverySource]] = None,
            limits: Optional[dict[str, int]] = None) -> dict:
    """`limits` maps a source_class value -> its own cap, overriding per_source_limit."""
    sources = sources or default_sources()
    limits = limits or {}
    collected = []
    per_source: dict[str, dict] = {}

    for src in sources:
        label = src.source_class.value
        cap = limits.get(label, per_source_limit)
        n = 0
        try:
            for cand in src.discover(cap):
                collected.append(cand)
                n += 1
            per_source[label] = {"yielded": n}
        except Exception as exc:  # one bad source must not sink the harvest
            log.error("source failed", extra={"event": "discover_error",
                                              "source": label, "error": str(exc), "yielded": n})
            per_source[label] = {"yielded": n, "error": str(exc)}

    # Evidence-based resolution (never silently merge; log every decision).
    resolved, decisions = EntityResolver().resolve(collected)
    unique_added = repo.add_candidates(resolved)

    multi_source = {r.name: r.discovery_sources for r in resolved if len(r.discovery_sources) > 1}
    action_counts: dict[str, int] = {}
    for d in decisions:
        action_counts[d.action] = action_counts.get(d.action, 0) + 1

    report = {
        "per_source": per_source,
        "total_yielded": len(collected),
        "resolved_firms": len(resolved),
        "unique_added": unique_added,
        "pool_size": repo.candidate_count(),
        "resolution": {
            "actions": action_counts,
            "multi_source_firm_count": len(multi_source),
            "multi_source_firms": multi_source,
            "decisions": [d.model_dump() for d in decisions],
        },
    }
    log.info("harvest complete", extra={"event": "harvest_done",
             "total_yielded": len(collected), "resolved_firms": len(resolved),
             "unique_added": unique_added, "pool_size": report["pool_size"],
             "merges": action_counts.get("merge", 0),
             "possible_dups": action_counts.get("possible_duplicate_kept_distinct", 0)})
    return report
