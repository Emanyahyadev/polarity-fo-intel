"""
Load delivered records for the RAG from the committed dataset CSV.

The RAG reads the same file a customer would receive (`data/final/family_offices.csv`),
so the served answers are reproducibly grounded in the exact delivered dataset.
Provenance/verification detail lives in the full pipeline; the retrieval + display
fields are reconstructed here.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Optional

from ..schema import Confidence, FamilyOfficeRecord, FOType, Signal, SourceClass

DEFAULT_CSV = "data/final/family_offices.csv"


def _date(s: str) -> date:
    try:
        return date.fromisoformat(s)
    except (ValueError, TypeError):
        return date.today()


def _enum(cls, value: str, default):
    try:
        return cls(value)
    except ValueError:
        return default


def _signals(row: dict) -> list[Signal]:
    out = []
    for i in (1, 2, 3):
        text = (row.get(f"recent_signal_{i}") or "").strip()
        if not text:
            continue
        d = row.get(f"recent_signal_{i}_date") or ""
        out.append(Signal(
            text=text, source_class=SourceClass.NEWS,
            event_date=date.fromisoformat(d) if d else None,
            source_url=(row.get(f"recent_signal_{i}_source") or None)))
    return out


def load_records_from_csv(path: str = DEFAULT_CSV) -> list[FamilyOfficeRecord]:
    rows = list(csv.DictReader(Path(path).read_text(encoding="utf-8").splitlines()))
    records: list[FamilyOfficeRecord] = []
    for row in rows:
        cnv = [f for f in (row.get("could_not_verify") or "").split("; ") if f]
        records.append(FamilyOfficeRecord(
            fo_id=row["fo_id"], name=row["family_office_name"],
            fo_type=_enum(FOType, row.get("fo_type", ""), FOType.UNDETERMINED),
            fo_type_evidence=row.get("classification_evidence") or None,
            description=row.get("description") or None,
            investment_thesis=row.get("investment_thesis") or None,
            investing_sectors=[s for s in (row.get("investing_sectors") or "").split("; ") if s],
            estimated_aum=row.get("estimated_aum") or None,
            website=row.get("website") or None,
            corporate_linkedin=row.get("corporate_linkedin") or None,
            hq_city=row.get("hq_city") or None, hq_state=row.get("hq_state") or None,
            hq_country=row.get("hq_country") or None, hq_phone=row.get("hq_phone") or None,
            principal_name=row.get("principal_name") or None,
            principal_title=row.get("principal_title") or None,
            principal_linkedin=row.get("principal_linkedin") or None,
            principal_phone=row.get("principal_phone") or None,
            signals=_signals(row),
            discovery_source=_enum(SourceClass, row.get("discovery_source", ""), SourceClass.OTHER),
            record_confidence=_enum(Confidence, row.get("record_confidence", ""), Confidence.LOW),
            data_as_of=_date(row.get("data_as_of", "")),
            could_not_verify=cnv))
    return records
