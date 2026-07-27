"""
Deliverable export — a clean, multi-sheet XLSX (+ a flat CSV of the main sheet).

Sheets:
  Dataset        — one row per family office (customer-facing view)
  Provenance     — per-cell lineage (Rule 1): field -> source/method/confidence/hash
  Sources        — discovery vs verification sources per firm (kept separate)
  Audit          — values withheld by validation (findings govern releases)
  Data Dictionary— what every column means, its source, and confidence semantics

Only gate-approved records should be passed here (the release gate is the authority).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .schema import AuditEntry, FamilyOfficeRecord

DATA_DICTIONARY = [
    ("fo_id", "Stable internal record id (deterministic from the firm key)."),
    ("family_office_name", "Firm legal/known name (anchored to the strongest authoritative source)."),
    ("fo_type", "Single-Family Office / Multi-Family Office / Undetermined (honest when type is unproven)."),
    ("classification_evidence", "The affirmative evidence that the firm IS a family office (Rule 2)."),
    ("description", "Short description (firm website; Wikipedia intro used only as cited background)."),
    ("investment_thesis", "Stated investing thesis/mandate where available."),
    ("investing_sectors", "Investing sectors (controlled vocabulary)."),
    ("estimated_aum", "AUM as stated on an authoritative source, with provenance."),
    ("website", "Official firm website (fetched and confirmed)."),
    ("corporate_linkedin", "Firm LinkedIn company page."),
    ("hq_city / hq_state / hq_country", "Headquarters location (SEC business address where available)."),
    ("hq_phone", "Authoritative firm main line (e.g. SEC filing) — verified contact intelligence."),
    ("principal_name / principal_title", "Decision-maker identity where verified."),
    ("principal_linkedin / principal_email / principal_phone", "Decision-maker contact; blank + could_not_verify when not verifiable."),
    ("principal_email_status", "deliverable / risky / could_not_verify (never a guessed 'verified')."),
    ("recent_signal_1..3 (+ _date, _source)", "Recent, dated activity (investments, hires, news)."),
    ("*_confidence", "Per-field confidence, derived from the cell's evidence (never inflated)."),
    ("discovery_source", "How the firm was FOUND (discovery ≠ verification)."),
    ("verification_sources", "Independent authoritative sources used to PROVE facts."),
    ("record_confidence", "Overall confidence — the weakest link across identity anchors."),
    ("data_as_of", "Date the record was validated."),
    ("could_not_verify", "Fields honestly left blank because they could not be verified."),
    ("reviewer_notes", "Human judgment notes (e.g. same-source justification)."),
]


def export_dataset(records: list[FamilyOfficeRecord], audit: list[AuditEntry],
                   out_dir: str = "data/final", basename: str = "family_offices") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    dataset = pd.DataFrame([r.to_delivery_row() for r in records])
    provenance = pd.DataFrame([row for r in records for row in r.provenance_rows()])
    sources = pd.DataFrame([row for r in records for row in r.source_rows()])
    audit_df = pd.DataFrame([a.model_dump() for a in audit]) if audit else pd.DataFrame(
        columns=["fo_id", "field", "rejected_value", "reason", "source_class", "checked_at"])
    ddict = pd.DataFrame(DATA_DICTIONARY, columns=["column", "meaning"])

    xlsx_path = out / f"{basename}.xlsx"
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as xw:
        dataset.to_excel(xw, sheet_name="Dataset", index=False)
        provenance.to_excel(xw, sheet_name="Provenance", index=False)
        sources.to_excel(xw, sheet_name="Sources", index=False)
        audit_df.to_excel(xw, sheet_name="Audit", index=False)
        ddict.to_excel(xw, sheet_name="Data Dictionary", index=False)

    csv_path = out / f"{basename}.csv"
    dataset.to_csv(csv_path, index=False, encoding="utf-8")

    return {"xlsx": str(xlsx_path), "csv": str(csv_path), "records": len(records),
            "provenance_rows": len(provenance), "audit_rows": len(audit_df)}
