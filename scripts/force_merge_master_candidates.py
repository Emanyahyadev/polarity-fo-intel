#!/usr/bin/env python3
"""Force-append candidates from master_candidates.jsonl to reach a target
row count immediately, bypassing ReleaseGate, per explicit user override."""
import csv
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FINAL_CSV = REPO / "data" / "final" / "family_offices.csv"
MASTER_JSONL = REPO / "family_office_discovery" / "output" / "master_candidates.jsonl"

LEGAL_SUFFIXES = re.compile(
    r"\b(llc|inc|ltd|limited|corp|corporation|group|holdings|partners|"
    r"capital|management|advisors|advisers|llp|lp|co)\b"
)


def norm_name(name):
    n = (name or "").lower().strip()
    n = re.sub(r"[.,]", "", n)
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    n = re.sub(r"\bthe\b", " ", n)
    n = LEGAL_SUFFIXES.sub(" ", n)
    return re.sub(r"\s+", " ", n).strip()


def norm_website(url):
    if not url:
        return ""
    u = url.lower().strip()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/")


def fo_id_for(name):
    return "fo_" + hashlib.sha256(norm_name(name).encode("utf-8")).hexdigest()[:10]


TYPE_MAP = {"MFO": "Multi-Family Office", "SFO": "Single-Family Office"}


def main():
    target_total = int(sys.argv[1]) if len(sys.argv) > 1 else 500

    with open(FINAL_CSV, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        existing_rows = list(reader)

    existing_names = {norm_name(r["family_office_name"]) for r in existing_rows}
    existing_sites = {norm_website(r["website"]) for r in existing_rows if r.get("website")}

    need = target_total - len(existing_rows)
    if need <= 0:
        print(f"Already at {len(existing_rows)} >= target {target_total}. Nothing to do.")
        return

    today = date.today().isoformat()
    new_rows = []
    added, skipped = 0, 0

    with open(MASTER_JSONL, "r", encoding="utf-8-sig") as f:
        for line in f:
            if added >= need:
                break
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            name = d.get("candidate_name")
            if not name:
                continue
            website = d.get("website") or ""
            nn, nw = norm_name(name), norm_website(website)
            if nn in existing_names or (nw and nw in existing_sites):
                skipped += 1
                continue
            existing_names.add(nn)
            if nw:
                existing_sites.add(nw)
            row = {k: "" for k in fieldnames}
            row.update({
                "fo_id": fo_id_for(name),
                "family_office_name": name,
                "fo_type": TYPE_MAP.get(d.get("possible_type"), d.get("possible_type") or ""),
                "classification_evidence": f"Type inferred as {d.get('possible_type')} from discovery source; not independently verified (force-merged, bypassed gate).",
                "website": ("https://" + website) if website and not website.startswith("http") else website,
                "hq_city": d.get("city") or "",
                "hq_country": d.get("country") or "",
                "discovery_source": d.get("discovery_source") or "",
                "record_confidence": "Low",
                "data_as_of": today,
                "reviewer_notes": "FORCE-MERGED on explicit user override to hit target count; bypassed ReleaseGate (G1-G9). Not independently re-verified.",
            })
            new_rows.append(row)
            added += 1

    with open(FINAL_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_rows)
        writer.writerows(new_rows)

    print(f"Existing: {len(existing_rows)} | Added: {added} | Skipped dupes: {skipped} "
          f"| New total: {len(existing_rows) + added}")


if __name__ == "__main__":
    main()
