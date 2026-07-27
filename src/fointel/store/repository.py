"""
Storage contract (the data layer boundary).

Business logic (pipeline, validation, RAG) depends ONLY on this interface, never
on a concrete database. That is what lets us develop on SQLite and deploy on
Postgres/Supabase with zero business-logic change (DecisionLog D5). No
SQLite- or Postgres-specific type may appear in a caller.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

from ..schema import AuditEntry, Candidate, FamilyOfficeRecord


class Repository(ABC):
    # --- lifecycle ---
    @abstractmethod
    def init_schema(self) -> None:
        """Create tables/indexes if absent. Idempotent."""

    def close(self) -> None:  # optional override
        pass

    # --- candidate pool (pre-validation) ---
    @abstractmethod
    def add_candidates(self, candidates: Iterable[Candidate]) -> int:
        """Persist candidates (de-duplicated by dedup_key). Returns number newly added."""

    @abstractmethod
    def all_candidates(self) -> list[Candidate]:
        ...

    @abstractmethod
    def candidate_count(self) -> int:
        ...

    # --- validated records (the product) ---
    @abstractmethod
    def upsert_record(self, record: FamilyOfficeRecord) -> None:
        ...

    @abstractmethod
    def get_record(self, fo_id: str) -> Optional[FamilyOfficeRecord]:
        ...

    @abstractmethod
    def all_records(self) -> list[FamilyOfficeRecord]:
        ...

    @abstractmethod
    def qualifying_records(self) -> list[FamilyOfficeRecord]:
        """Records that pass Rule 2 (qualifies() == True)."""

    # --- audit trail (withheld values; findings govern releases) ---
    @abstractmethod
    def add_audit(self, entry: AuditEntry) -> None:
        ...

    @abstractmethod
    def all_audit(self) -> list[AuditEntry]:
        ...
