#!/usr/bin/env python3
"""Force-append ALL raw browser-use candidates (both batches) into the
canonical CSV immediately, bypassing ReleaseGate, per explicit user override."""
import csv
import hashlib
import json
import re
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FINAL_CSV = REPO / "data" / "final" / "family_offices.csv"
ENRICHED_JSONL = REPO / "family_office_discovery" / "output" / "contacts_enriched.jsonl"
NEW_COUNTRIES_JSONL = REPO / "family_office_discovery" / "output" / "new_countries_candidates.jsonl"

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
    with open(FINAL_CSV, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        existing_rows = list(reader)

    existing_names = {norm_name(r["family_office_name"]) for r in existing_rows}
    existing_sites = {norm_website(r["website"]) for r in existing_rows if r.get("website")}

    today = date.today().isoformat()
    new_rows = []
    added, skipped = 0, 0

    # Batch 1: enriched candidates (has principal/contact detail)
    with open(ENRICHED_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            c = json.loads(line)
            e = c.get("enrichment")
            if not e:
                continue
            name = c.get("candidate_name", "")
            website = c.get("website", "")
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
                "fo_type": TYPE_MAP.get(c.get("possible_type"), c.get("possible_type") or ""),
                "classification_evidence": f"Type inferred as {c.get('possible_type')} from discovery source; not independently verified (force-merged, bypassed gate).",
                "description": e.get("short_description") or "",
                "website": ("https://" + website) if website and not website.startswith("http") else website,
                "corporate_linkedin": e.get("family_office_linkedin_url") or "",
                "hq_city": c.get("city") or "",
                "hq_country": c.get("country") or "",
                "hq_phone": e.get("contact_phone") or "",
                "principal_name": e.get("principal_full_name") or "",
                "principal_title": e.get("principal_job_title") or "",
                "principal_linkedin": e.get("principal_linkedin_url") or "",
                "firm_contact_email": e.get("contact_email") or "",
                "discovery_source": c.get("discovery_source") or "browser-use.com cloud agent",
                "verification_sources": "; ".join(e.get("sources") or []),
                "record_confidence": (e.get("confidence") or "Medium").capitalize(),
                "data_as_of": today,
                "reviewer_notes": "FORCE-MERGED on explicit user override; bypassed ReleaseGate (G1-G9). Not independently re-verified.",
            })
            new_rows.append(row)
            added += 1

    # Batch 2: new-country discovery candidates (no contact enrichment)
    with open(NEW_COUNTRIES_JSONL, "r", encoding="utf-8") as f:
        for line in f:
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
                "discovery_source": d.get("discovery_source") or "browser-use.com cloud agent (new-country discovery)",
                "record_confidence": "Low",
                "data_as_of": today,
                "reviewer_notes": "FORCE-MERGED on explicit user override; bypassed ReleaseGate (G1-G9). Not independently re-verified.",
            })
            new_rows.append(row)
            added += 1

    with open(FINAL_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_rows)
        writer.writerows(new_rows)

    print(f"Existing: {len(existing_rows)} | Added: {added} | Skipped dupes: {skipped} "
          f"| New total: {len(existing_rows) + added}")


if __name__ == "__main__":
    main()
