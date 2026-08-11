#!/usr/bin/env python3
"""
Merge browser-use-enriched family office candidates into the project's
canonical data/final/family_offices.csv (49-column schema), deduping
against the existing records by normalized name / website.
"""
import csv
import hashlib
import json
import re
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
FINAL_CSV = REPO / "data" / "final" / "family_offices.csv"
ENRICHED_JSONL = REPO / "family_office_discovery" / "output" / "contacts_enriched.jsonl"

LEGAL_SUFFIXES = re.compile(
    r"\b(llc|inc|ltd|limited|corp|corporation|group|holdings|partners|"
    r"capital|management|advisors|advisers|llp|lp|co)\b"
)


def norm_name(name: str) -> str:
    n = (name or "").lower().strip()
    n = re.sub(r"[.,]", "", n)
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    n = re.sub(r"\bthe\b", " ", n)
    n = LEGAL_SUFFIXES.sub(" ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def norm_website(url: str) -> str:
    if not url:
        return ""
    u = url.lower().strip()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/")


def fo_id_for(name: str) -> str:
    return "fo_" + hashlib.sha256(norm_name(name).encode("utf-8")).hexdigest()[:10]


TYPE_MAP = {"MFO": "Multi-Family Office", "SFO": "Single-Family Office"}


def main():
    with open(FINAL_CSV, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        existing_rows = list(reader)

    existing_names = {norm_name(r["family_office_name"]) for r in existing_rows}
    existing_sites = {norm_website(r["website"]) for r in existing_rows if r.get("website")}

    candidates = []
    with open(ENRICHED_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("enrichment"):
                candidates.append(r)

    today = date.today().isoformat()
    added, skipped_dupe = 0, 0
    new_rows = []

    for c in candidates:
        name = c.get("candidate_name", "")
        website = c.get("website", "")
        nn = norm_name(name)
        nw = norm_website(website)
        if nn in existing_names or (nw and nw in existing_sites):
            skipped_dupe += 1
            continue

        e = c["enrichment"]
        conf = (e.get("confidence") or "medium").strip().capitalize()
        if conf not in ("High", "Medium", "Low"):
            conf = "Medium"

        missing = []
        for field, val in [
            ("estimated_aum", ""), ("investment_thesis", ""), ("investing_sectors", ""),
            ("hq_state", ""), ("recent_signal_1", ""), ("recent_signal_2", ""),
            ("recent_signal_3", ""), ("principal_email", ""), ("principal_phone", ""),
        ]:
            missing.append(field)

        row = {k: "" for k in fieldnames}
        row.update({
            "fo_id": fo_id_for(name),
            "family_office_name": name,
            "fo_type": TYPE_MAP.get(c.get("possible_type"), c.get("possible_type") or ""),
            "classification_evidence": f"Type inferred as {c.get('possible_type')} from discovery source; not independently verified.",
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
            "firm_contact_email_status": "unverified" if e.get("contact_email") else "",
            "name_confidence": "Medium",
            "fo_type_confidence": "Low",
            "principal_name_confidence": conf if e.get("principal_full_name") else "",
            "firm_contact_email_confidence": conf if e.get("contact_email") else "",
            "website_confidence": "High" if website else "",
            "corporate_linkedin_confidence": conf if e.get("family_office_linkedin_url") else "",
            "principal_linkedin_confidence": conf if e.get("principal_linkedin_url") else "",
            "discovery_source": c.get("discovery_source") or "browser-use.com cloud agent",
            "verification_sources": "; ".join(e.get("sources") or []),
            "record_confidence": conf,
            "data_as_of": today,
            "could_not_verify": "; ".join(missing),
            "reviewer_notes": "Discovered via directory sweep + enriched by an automated browser-use.com "
                               "cloud agent researching public web sources. Not yet reviewed by an analyst.",
        })
        new_rows.append(row)
        existing_names.add(nn)
        if nw:
            existing_sites.add(nw)
        added += 1

    with open(FINAL_CSV, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(existing_rows)
        writer.writerows(new_rows)

    print(f"Existing: {len(existing_rows)} | Added: {added} | Skipped as duplicates: {skipped_dupe} "
          f"| New total: {len(existing_rows) + added}")


if __name__ == "__main__":
    main()
