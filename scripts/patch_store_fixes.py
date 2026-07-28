"""
Small store patches from the review board (operates on data/final/records.json):
  * Geller Advisors' 13F signals lacked a source_url (its CIK wasn't in the candidate map).
    Attach the real SEC EDGAR 13F filing-list URL (CIK 1354739, confirmed via EDGAR) to its
    signals and add an EDGAR verification source.
  * Scan every record for a dated signal without a source_url (now a provenance violation).
Idempotent. Re-serialize the store; re-export separately.
    py -3.12 scripts/patch_store_fixes.py
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fointel.rag.load import load_records_from_store             # noqa: E402
from fointel.schema import SourceClass, SourceRef               # noqa: E402

AS_OF = date(2026, 7, 28)
# CIK overrides for 13F filers missing from the candidate identifier map (verified on EDGAR).
CIK_OVERRIDE = {"Geller Advisors LLC": "1354739"}


def edgar_13f(cik):
    return (f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"
            f"&type=13F&dateb=&owner=include&count=40")


def main():
    records = load_records_from_store()
    for rec in records:
        cik = CIK_OVERRIDE.get(rec.name)
        if cik:
            for s in rec.signals:
                if not s.source_url:
                    s.source_url = edgar_13f(cik)
            if not any(v.source_class == SourceClass.SEC_EDGAR for v in rec.verification_sources):
                rec.verification_sources.append(SourceRef(
                    source_class=SourceClass.SEC_EDGAR,
                    verifies="13F holdings / recent portfolio activity", accessed_at=AS_OF,
                    url=edgar_13f(cik)))

    missing = [(r.name, i) for r in records for i, s in enumerate(r.signals) if not s.source_url]
    viol = [(r.name, v) for r in records for v in r.provenance_violations()]
    print("signals still missing source_url:", missing or "none")
    print("provenance violations:", viol or "none")
    assert not missing and not viol, "unresolved signal/provenance gaps"

    Path("data/final/records.json").write_text(
        json.dumps([r.model_dump(mode="json") for r in records], indent=1, ensure_ascii=False),
        encoding="utf-8")
    print("store patched OK")


if __name__ == "__main__":
    main()
