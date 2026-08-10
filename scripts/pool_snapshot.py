"""Export / import the candidate POOL so it survives between runs.

Why this exists (found 2026-08-10): the pool lives in `data/fointel.db`, which is
gitignored ("regenerable by the pipeline"). On a hosted runner every scheduled
run therefore starts with an EMPTY pool, re-discovers the same firms from the
same free-tier sources, and throws the accumulated work away when the job ends.
That is why the released set sat at 80 records across hundreds of cycles while
a local pool had grown to 612 candidates: discovery was never the bottleneck,
pool amnesia was.

The pool is a working queue of *candidates*, not the deliverable. It holds only
what the public sources already publish — firm name, source class, source URL,
and cheap hints (city/state, CIK/EIN). It is exported as sorted JSON (not the
binary .db) so the diff is reviewable and the file stays merge-friendly.

    python scripts/pool_snapshot.py export    # DB  -> data/pool/candidates.json
    python scripts/pool_snapshot.py import    # JSON -> DB (idempotent, additive)

`import` never deletes: it inserts candidates the DB does not already hold,
keyed by dedup_key, so re-running it is a no-op and a run that discovered new
firms still keeps them.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "fointel.db"
SNAPSHOT = ROOT / "data" / "pool" / "candidates.json"


def _connect() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB)


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS candidates ("
        "dedup_key TEXT PRIMARY KEY, name TEXT, source_class TEXT, payload TEXT)")


def export_pool() -> int:
    if not DB.exists():
        print(f"no database at {DB}; nothing to export")
        return 0
    conn = _connect()
    _ensure_table(conn)
    rows = conn.execute(
        "SELECT dedup_key, name, source_class, payload FROM candidates "
        "ORDER BY dedup_key").fetchall()
    out = [{"dedup_key": k, "name": n, "source_class": s, "payload": json.loads(p) if p else {}}
           for k, n, s, p in rows]
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False),
                        encoding="utf-8")
    print(f"exported {len(out)} candidates -> {SNAPSHOT.relative_to(ROOT)}")
    return len(out)


def import_pool() -> int:
    if not SNAPSHOT.exists():
        print(f"no snapshot at {SNAPSHOT}; starting with whatever the DB holds")
        return 0
    data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    conn = _connect()
    _ensure_table(conn)
    existing = {r[0] for r in conn.execute("SELECT dedup_key FROM candidates")}
    added = 0
    for c in data:
        key = c.get("dedup_key")
        if not key or key in existing:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO candidates (dedup_key, name, source_class, payload) "
            "VALUES (?, ?, ?, ?)",
            (key, c.get("name"), c.get("source_class"),
             json.dumps(c.get("payload") or {}, ensure_ascii=False)))
        added += 1
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    print(f"seeded {added} new candidates from snapshot; pool now holds {total}")
    return added


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "export":
        export_pool()
    elif mode == "import":
        import_pool()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
