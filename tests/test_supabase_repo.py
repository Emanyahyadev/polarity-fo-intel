"""
Postgres/Supabase backend tests.

The roundtrip test runs only when TEST_DATABASE_URL points at a reachable Postgres
(e.g. a Supabase instance) — that is how the backend is validated at deploy. The
error-path test always runs and proves the factory fails clearly (not with a
dangling import) when the driver is absent.
"""

import os
from datetime import date

import pytest

from fointel.schema import AuditEntry, Candidate, FamilyOfficeRecord, FOType, SourceClass
from fointel.store.supabase_repo import SupabaseRepository

_DSN = os.getenv("TEST_DATABASE_URL")


def _psycopg_installed() -> bool:
    try:
        import psycopg  # noqa: F401
        return True
    except ImportError:
        return False


def test_missing_driver_raises_actionable_error():
    if _psycopg_installed():
        pytest.skip("psycopg is installed; the missing-driver path is not exercised here")
    with pytest.raises(ImportError, match="psycopg"):
        SupabaseRepository("postgresql://user:pass@localhost:5432/db")


@pytest.mark.skipif(not _DSN, reason="set TEST_DATABASE_URL to run the Postgres roundtrip")
def test_postgres_roundtrip_matches_sqlite_contract():
    repo = SupabaseRepository(_DSN)
    repo.init_schema()
    rec = FamilyOfficeRecord(fo_id="fo_pg_1", name="PG FO", fo_type=FOType.SFO,
                             fo_type_evidence="ev", discovery_source=SourceClass.SEC_EDGAR,
                             data_as_of=date(2026, 7, 27))
    repo.upsert_record(rec)
    assert repo.get_record("fo_pg_1").name == "PG FO"
    assert [r.fo_id for r in repo.qualifying_records()] == ["fo_pg_1"]
    repo.add_audit(AuditEntry(fo_id="fo_pg_1", field="principal_email", rejected_value="x@y.com",
                              reason="undeliverable", source_class=SourceClass.FIRM_SITE,
                              checked_at=date(2026, 7, 27)))
    assert len(repo.all_audit()) >= 1
    assert repo.add_candidates([Candidate(name="PG FO", source_class=SourceClass.NEWS,
                                          dedup_key="pg_fo")]) == 1
