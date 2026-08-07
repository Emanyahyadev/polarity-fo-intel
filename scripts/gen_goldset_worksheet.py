"""
Generate a human review worksheet for the machine-drafted gold set.

The gold set (`goldset/firm_type_goldset.jsonl`) is DRAFT and requires the
candidate's review/confirmation. This script renders every gold-set record -- with
the machine-drafted type, the current served-record facts, and empty review columns
-- into `goldset/review_worksheet.md` for the candidate to complete. It does NOT
modify the gold-set file and it makes no confirmation on anyone's behalf.

    python scripts/gen_goldset_worksheet.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "goldset" / "firm_type_goldset.jsonl"
OUT = ROOT / "goldset" / "review_worksheet.md"
CSV = ROOT / "data" / "final" / "family_offices.csv"


def _load_gold() -> list[dict]:
    rows = []
    for line in GOLD.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def _load_records() -> dict[str, dict]:
    if not CSV.exists():
        return {}
    out: dict[str, dict] = {}
    with open(CSV, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("family_office_name") or row.get("name") or "").strip()
            if name:
                out[name.lower()] = {k: (v or "") for k, v in row.items()}
    return out


def _enrich(gold: list[dict], records: dict[str, dict]) -> list[dict]:
    out = []
    for i, g in enumerate(gold, 1):
        row = dict(g)
        rec = records.get(row["firm_name"].strip().lower())
        row["n"] = i
        row["in_delivered"] = "yes" if rec else "no"
        row["served_type"] = ""
        row["served_evidence"] = ""
        if rec:
            row["served_type"] = rec.get("fo_type", "")
            row["served_evidence"] = (rec.get("classification_evidence") or "")[:140]
        else:
            row["served_type"] = ""
            row["served_evidence"] = ""
        out.append(row)
    return out


def render(rows: list[dict], n_gold: int) -> str:
    lines = ["# Gold-set Review Worksheet (machine-drafted, DRAFT)",
             "",
             f"Generated from `goldset/firm_type_goldset.jsonl` ({n_gold} records) by "
             "`scripts/gen_goldset_worksheet.py` on a deterministic export of the "
             "committed data. The gold set is **DRAFT** and requires the candidate's "
             "review/confirmation (human judgment). This worksheet is the review vehicle; "
             "the gold-set file itself is not modified.",
             "",
             "## Instructions (candidate)",
             "",
             "For **every** row, confirm or correct the machine-drafted answer in the "
             "review columns. A gold-set record is only considered confirmed once you "
             "have answered it here. Leave `Is a family office?` / `True type` blank only "
             "if you explicitly defer that row (record why).",
             "",
             "| # | Firm | Mach. says FO? | Mach. true type | In delivery | Served type | Served evidence (truncated) |",
             "|---|------|----------------|-----------------|-------------|-------------|------------------------------|",
             "|   |       |                |                 |             |             |                              |"]
    for r in rows:
        true_type = r.get("true_type") or ""
        lines.append(
            f"| {r['n']} | {r['firm_name']} | "
            f"{'Yes' if r.get('is_family_office') else 'No'} | {true_type} | "
            f"{r['in_delivered']} | {r.get('served_type') or ''} | "
            f"{(r.get('served_evidence') or '').replace('|','/')} |")
    lines += [
        "",
        "## Review columns to fill (in your own copy, or answer in a reply)",
        "",
        "- Confirmed as family office: (yes / no / needs work)",
        "- Confirmed true type (SFO / MFO / Undetermined / not a family office): ",
        "- Evidence checked: ",
        "- Notes: ",
        "- Reviewer: <name>  - Date: <date>",
        "",
        "> This worksheet is a review aid only. It does not confirm anything and ",
        "> is not itself the gold set. Confirm the gold set only by updating ",
        "> `firm_type_goldset.jsonl` after human review.",
    ]
    return "\n".join(lines)


def main() -> None:
    gold = _load_gold()
    records = _load_records()
    rows = _enrich(gold, records)
    OUT.write_text(render(rows, len(gold)), encoding="utf-8")
    print(f"Wrote {OUT} ({len(rows)} rows; {len([r for r in rows if r['in_delivered']=='yes'])} in delivered set)")


if __name__ == "__main__":
    main()