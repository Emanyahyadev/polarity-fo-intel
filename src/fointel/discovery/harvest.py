"""
Candidate harvest: run every discovery source, de-duplicate across them, persist
the pool, and report the per-source distribution + cross-source overlap.

The distribution report is the evidence that discovery is genuinely multi-source
(no single source dominates) — the assessment's load-bearing anti-"copy at scale"
check. A source that raises is logged and skipped, never allowed to fail silently.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from ..observability import get_logger
from ..store import Repository
from .base import DiscoverySource
from .directory import DirectorySource
from .irs_990pf import Irs990pfSource
from .news import NewsSource
from .sec_edgar import SecEdgarSource

log = get_logger("pipeline")


def default_sources() -> list[DiscoverySource]:
    return [SecEdgarSource(), Irs990pfSource(), DirectorySource(), NewsSource()]


def harvest(repo: Repository, per_source_limit: int,
            sources: Optional[list[DiscoverySource]] = None,
            limits: Optional[dict[str, int]] = None) -> dict:
    """`limits` maps a source_class value -> its own cap, overriding per_source_limit."""
    sources = sources or default_sources()
    limits = limits or {}
    found_by: dict[str, set[str]] = defaultdict(set)
    collected = []
    per_source: dict[str, dict] = {}

    for src in sources:
        label = src.source_class.value
        cap = limits.get(label, per_source_limit)
        n = 0
        try:
            for cand in src.discover(cap):
                found_by[cand.dedup_key or cand.name].add(label)
                collected.append(cand)
                n += 1
            per_source[label] = {"yielded": n}
        except Exception as exc:  # one bad source must not sink the harvest
            log.error("source failed", extra={"event": "discover_error",
                                              "source": label, "error": str(exc), "yielded": n})
            per_source[label] = {"yielded": n, "error": str(exc)}

    unique_added = repo.add_candidates(collected)
    multi_source = {k: sorted(v) for k, v in found_by.items() if len(v) > 1}

    report = {
        "per_source": per_source,
        "total_yielded": len(collected),
        "unique_added": unique_added,
        "pool_size": repo.candidate_count(),
        "multi_source_firm_count": len(multi_source),
        "multi_source_firms": multi_source,
    }
    log.info("harvest complete", extra={"event": "harvest_done", **{
        "total_yielded": report["total_yielded"], "unique_added": unique_added,
        "pool_size": report["pool_size"], "multi_source": len(multi_source)}})
    return report
