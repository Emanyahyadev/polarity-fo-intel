"""
Re-export the delivered CSV + XLSX + embeddings from the canonical lossless store
(data/final/records.json) + persisted audit trail (data/final/audit.json), WITHOUT
re-running the transform. Use this for export-only changes (e.g. Data Dictionary text)
so the data is never re-mutated. Idempotent.

    py -3.12 scripts/reexport_from_store.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fointel.export import export_dataset                        # noqa: E402
from fointel.rag.index import precompute_and_save                # noqa: E402
from fointel.rag.load import load_records_from_store             # noqa: E402
from fointel.schema import AuditEntry, SourceClass               # noqa: E402

AUDIT = Path("data/final/audit.json")


def load_audit():
    if AUDIT.exists():
        return [AuditEntry.model_validate(a)
                for a in json.loads(AUDIT.read_text(encoding="utf-8"))]
    # fall back to recovering the audit trail from the current xlsx Audit sheet
    import openpyxl
    wb = openpyxl.load_workbook("data/final/family_offices.xlsx", read_only=True)
    out = []
    def _sc(v):
        v = str(v)
        return SourceClass[v.split(".", 1)[1]] if v.startswith("SourceClass.") else SourceClass(v)
    for row in wb["Audit"].iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        out.append(AuditEntry(fo_id=row[0], field=row[1], rejected_value=str(row[2]),
                              reason=row[3], source_class=_sc(row[4]),
                              checked_at=date.fromisoformat(str(row[5])[:10])))
    AUDIT.write_text(json.dumps([a.model_dump(mode="json") for a in out], indent=1),
                     encoding="utf-8")   # persist for next time
    return out


def main():
    records = load_records_from_store()
    audit = load_audit()
    res = export_dataset(records, audit=audit, out_dir="data/final")
    precompute_and_save(records)
    print(f"re-exported {res['records']} records | provenance rows {res['provenance_rows']} "
          f"| audit rows {len(audit)}")


if __name__ == "__main__":
    main()
