"""Data layer. Callers depend on `Repository`; the concrete backend is chosen here."""

from __future__ import annotations

import os

from ..config import settings
from .repository import Repository
from .sqlite_repo import SqliteRepository

__all__ = ["Repository", "SqliteRepository", "get_repository"]


def get_repository() -> Repository:
    """Return the active repository.

    SQLite is the local/dev default. When `DATABASE_URL` (Supabase/Postgres) is
    set — wired at deployment — the Postgres implementation is selected instead.
    Callers never see the difference.
    """
    if os.getenv("DATABASE_URL"):
        from .supabase_repo import SupabaseRepository  # psycopg imported lazily inside

        repo: Repository = SupabaseRepository(os.environ["DATABASE_URL"])
    else:
        repo = SqliteRepository(settings.db_path)
    repo.init_schema()
    return repo
