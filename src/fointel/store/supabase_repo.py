"""
Postgres / Supabase implementation of Repository (production / deploy backend).

Mirrors the SQLite backend exactly (same tables, JSON payload + indexed columns)
but uses Postgres `jsonb`, so switching backends is a config change — set
`DATABASE_URL` — with zero business-logic change (DecisionLog D5).

`psycopg` is imported lazily inside __init__ so importing this module never fails;
if the driver is absent the error is clear and actionable. Validated against a
live Supabase instance at deploy (Wave 3); a conditional integration test
(tests/test_supabase_repo.py, skipped unless TEST_DATABASE_URL is set) exercises
it wherever a Postgres instance is available.
"""

from __future__ import annotations

from typing import Iterable, Optional

from ..schema import AuditEntry, Candidate, FamilyOfficeRecord
from ..text import norm_name
from .repository import Repository


class SupabaseRepository(Repository):
    def __init__(self, dsn: str):
        try:
            import psycopg
            from psycopg.types.json import Jsonb
        except ImportError as exc:  # clear, actionable — never a dangling import
            raise ImportError(
                "SupabaseRepository requires psycopg. Install it with: "
                "pip install 'psycopg[binary]'"
            ) from exc
        self._Jsonb = Jsonb
        self._conn = psycopg.connect(dsn, autocommit=True)

    def init_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS candidates (
                    dedup_key    text PRIMARY KEY,
                    name         text NOT NULL,
                    source_class text NOT NULL,
                    payload      jsonb NOT NULL
                );""")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    fo_id             text PRIMARY KEY,
                    name              text NOT NULL,
                    fo_type           text,
                    hq_state          text,
                    hq_country        text,
                    qualifies         boolean NOT NULL DEFAULT false,
                    record_confidence text,
                    payload           jsonb NOT NULL
                );""")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_records_type ON records(fo_type);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_records_qualifies ON records(qualifies);")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS audit (
                    id      bigserial PRIMARY KEY,
                    fo_id   text NOT NULL,
                    field   text NOT NULL,
                    reason  text NOT NULL,
                    payload jsonb NOT NULL
                );""")

    def close(self) -> None:
        self._conn.close()

    # --- candidates ---
    def add_candidates(self, candidates: Iterable[Candidate]) -> int:
        added = 0
        with self._conn.cursor() as cur:
            for cand in candidates:
                key = cand.dedup_key or norm_name(cand.name)
                cur.execute(
                    "INSERT INTO candidates(dedup_key, name, source_class, payload) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (dedup_key) DO NOTHING",
                    (key, cand.name, cand.source_class.value,
                     self._Jsonb(cand.model_dump(mode="json"))),
                )
                added += cur.rowcount
        return added

    def all_candidates(self) -> list[Candidate]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM candidates")
            return [Candidate.model_validate(r[0]) for r in cur.fetchall()]

    def candidate_count(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM candidates")
            return cur.fetchone()[0]

    # --- records ---
    def upsert_record(self, record: FamilyOfficeRecord) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO records(fo_id, name, fo_type, hq_state, hq_country,
                                       qualifies, record_confidence, payload)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (fo_id) DO UPDATE SET
                     name=EXCLUDED.name, fo_type=EXCLUDED.fo_type, hq_state=EXCLUDED.hq_state,
                     hq_country=EXCLUDED.hq_country, qualifies=EXCLUDED.qualifies,
                     record_confidence=EXCLUDED.record_confidence, payload=EXCLUDED.payload""",
                (record.fo_id, record.name, record.fo_type.value, record.hq_state,
                 record.hq_country, record.qualifies(), record.record_confidence.value,
                 self._Jsonb(record.model_dump(mode="json"))),
            )

    def get_record(self, fo_id: str) -> Optional[FamilyOfficeRecord]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM records WHERE fo_id=%s", (fo_id,))
            row = cur.fetchone()
            return FamilyOfficeRecord.model_validate(row[0]) if row else None

    def all_records(self) -> list[FamilyOfficeRecord]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM records ORDER BY fo_id")
            return [FamilyOfficeRecord.model_validate(r[0]) for r in cur.fetchall()]

    def qualifying_records(self) -> list[FamilyOfficeRecord]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM records WHERE qualifies=true ORDER BY fo_id")
            return [FamilyOfficeRecord.model_validate(r[0]) for r in cur.fetchall()]

    # --- audit ---
    def add_audit(self, entry: AuditEntry) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO audit(fo_id, field, reason, payload) VALUES (%s, %s, %s, %s)",
                (entry.fo_id, entry.field, entry.reason,
                 self._Jsonb(entry.model_dump(mode="json"))),
            )

    def all_audit(self) -> list[AuditEntry]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT payload FROM audit ORDER BY id")
            return [AuditEntry.model_validate(r[0]) for r in cur.fetchall()]
