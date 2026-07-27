"""
SQLite implementation of Repository (development / local runs).

Records are stored as a JSON payload plus a few extracted, indexed columns for
structured retrieval (fo_type, geography, confidence). The same JSON-plus-indexed
shape ports directly to Postgres `jsonb` + generated columns, so the Supabase
implementation is a drop-in with no caller change (DecisionLog D5).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Optional

from ..schema import AuditEntry, Candidate, FamilyOfficeRecord
from ..text import norm_name
from .repository import Repository


class SqliteRepository(Repository):
    def __init__(self, db_path: str = "data/fointel.db") -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")

    # --- lifecycle ---
    def init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                dedup_key    TEXT PRIMARY KEY,
                name         TEXT NOT NULL,
                source_class TEXT NOT NULL,
                payload      TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS records (
                fo_id            TEXT PRIMARY KEY,
                name             TEXT NOT NULL,
                fo_type          TEXT,
                hq_state         TEXT,
                hq_country       TEXT,
                qualifies        INTEGER NOT NULL DEFAULT 0,
                record_confidence TEXT,
                payload          TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_records_type ON records(fo_type);
            CREATE INDEX IF NOT EXISTS idx_records_qualifies ON records(qualifies);
            CREATE TABLE IF NOT EXISTS audit (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                fo_id        TEXT NOT NULL,
                field        TEXT NOT NULL,
                reason       TEXT NOT NULL,
                payload      TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- candidates ---
    def add_candidates(self, candidates: Iterable[Candidate]) -> int:
        added = 0
        for cand in candidates:
            key = cand.dedup_key or norm_name(cand.name)
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO candidates(dedup_key, name, source_class, payload) "
                "VALUES (?, ?, ?, ?)",
                (key, cand.name, cand.source_class.value, cand.model_dump_json()),
            )
            added += cur.rowcount
        self._conn.commit()
        return added

    def all_candidates(self) -> list[Candidate]:
        rows = self._conn.execute("SELECT payload FROM candidates").fetchall()
        return [Candidate.model_validate_json(r["payload"]) for r in rows]

    def candidate_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) AS n FROM candidates").fetchone()["n"]

    # --- records ---
    def upsert_record(self, record: FamilyOfficeRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO records(fo_id, name, fo_type, hq_state, hq_country,
                                qualifies, record_confidence, payload)
            VALUES (:fo_id, :name, :fo_type, :hq_state, :hq_country,
                    :qualifies, :record_confidence, :payload)
            ON CONFLICT(fo_id) DO UPDATE SET
                name=excluded.name, fo_type=excluded.fo_type, hq_state=excluded.hq_state,
                hq_country=excluded.hq_country, qualifies=excluded.qualifies,
                record_confidence=excluded.record_confidence, payload=excluded.payload
            """,
            {
                "fo_id": record.fo_id,
                "name": record.name,
                "fo_type": record.fo_type.value,
                "hq_state": record.hq_state,
                "hq_country": record.hq_country,
                "qualifies": int(record.qualifies()),
                "record_confidence": record.record_confidence.value,
                "payload": record.model_dump_json(),
            },
        )
        self._conn.commit()

    def get_record(self, fo_id: str) -> Optional[FamilyOfficeRecord]:
        row = self._conn.execute("SELECT payload FROM records WHERE fo_id=?", (fo_id,)).fetchone()
        return FamilyOfficeRecord.model_validate_json(row["payload"]) if row else None

    def all_records(self) -> list[FamilyOfficeRecord]:
        rows = self._conn.execute("SELECT payload FROM records ORDER BY fo_id").fetchall()
        return [FamilyOfficeRecord.model_validate_json(r["payload"]) for r in rows]

    def qualifying_records(self) -> list[FamilyOfficeRecord]:
        rows = self._conn.execute(
            "SELECT payload FROM records WHERE qualifies=1 ORDER BY fo_id"
        ).fetchall()
        return [FamilyOfficeRecord.model_validate_json(r["payload"]) for r in rows]

    # --- audit ---
    def add_audit(self, entry: AuditEntry) -> None:
        self._conn.execute(
            "INSERT INTO audit(fo_id, field, reason, payload) VALUES (?, ?, ?, ?)",
            (entry.fo_id, entry.field, entry.reason, entry.model_dump_json()),
        )
        self._conn.commit()

    def all_audit(self) -> list[AuditEntry]:
        rows = self._conn.execute("SELECT payload FROM audit ORDER BY id").fetchall()
        return [AuditEntry.model_validate_json(r["payload"]) for r in rows]
