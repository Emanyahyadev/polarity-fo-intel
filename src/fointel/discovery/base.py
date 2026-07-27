"""
Discovery layer contract.

A DiscoverySource answers the question: "which firms might be family offices?"
It is deliberately NOT responsible for proving anything — that is the job of the
enrichment and validation layers. Keeping discovery and proof separate is a
requirement of the assessment ("use each source only for the job it can do").

Each source emits `Candidate` objects (defined in schema) with a raw payload
preserved for provenance.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

from ..schema import Candidate, SourceClass
from ..text import norm_name as dedup_key  # re-exported for discovery sources

__all__ = ["Candidate", "DiscoverySource", "dedup_key"]


class DiscoverySource(ABC):
    """Base class for a single discovery channel (SEC ADV, IRS 990-PF, News, Directory)."""

    source_class: SourceClass

    @abstractmethod
    def discover(self, limit: int) -> Iterator[Candidate]:
        """Yield up to `limit` candidate firms. Must fail loudly, never silently."""
        raise NotImplementedError

    @property
    def name(self) -> str:
        return type(self).__name__
