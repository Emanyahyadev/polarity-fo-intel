"""
Parse the SEC bulk Form ADV data into data/adv/adv_facts.json — the lookup the AdvEnricher
reads (total AUM + owner-principal per CRD, for registered family offices that don't file 13F).

WHY a pre-parsed lookup: the SEC ADV Part 1 bulk file is ~700 MB (all advisers, 2011-2024);
downloading/parsing it at pipeline runtime is impractical, so we parse it once, offline, into
a tiny committed JSON. It is fully REPRODUCIBLE from the authoritative source below.

Source (authoritative, free — SEC Form ADV Data):
  https://www.sec.gov/files/adv-filing-data-20111105-20241231-part1.zip
    IA_ADV_Base_A_*.csv   -> 1E1 (CRD), DateSubmitted, FilingID, 5F2c (total regulatory AUM)
    IA_Schedule_A_B_*.csv -> FilingID, Full Legal Name, Title or Status, Ownership Code,
                             Control Person, DE/FE/I

Usage:
  # 1) download the zip once (SEC requires a descriptive UA):
  #    curl -H "User-Agent: you you@example.com" -o adv_part1.zip <url above>
  # 2) parse it for the delivered firms:
  py -3.12 scripts/parse_adv_bulk.py adv_part1.zip

Only firms present in the delivered dataset (matched by CRD from the candidate pool) and with
a filing >= 2021 (freshness — an older filing's owner/AUM may be stale) are kept.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

FRESH_FROM_YEAR = 2021
OUT = Path("data/adv/adv_facts.json")
_OWN_RANK = {"E": 5, "D": 4, "C": 3, "B": 2, "A": 1, "": 0}


def our_crds() -> dict:
    """CRD -> firm name, for the firms in the delivered dataset (from the candidate pool)."""
    rows = list(csv.DictReader(Path("data/final/family_offices.csv").read_text(
        encoding="utf-8").splitlines()))
    names = {r["family_office_name"].upper() for r in rows}
    con = sqlite3.connect("data/fointel.db")
    out = {}
    for name, payload in con.execute("SELECT name, payload FROM candidates"):
        if name.upper() not in names:
            continue
        try:
            p = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            continue
        crd = p.get("crd") or (p.get("raw") or {}).get("crd")
        if crd:
            out[str(crd)] = name
    return out


def _year(ds: str) -> int:
    m = re.search(r"/(\d{4})", ds or "")
    return int(m.group(1)) if m else 0


def _fmt_name(s: str) -> str:
    parts = [p.strip().title() for p in s.split(",") if p.strip()]
    return " ".join(parts[1:] + [parts[0]]) if len(parts) >= 2 else s.title()


def _open(z, needle):
    name = next((n for n in z.namelist() if needle in n), None)
    return io.TextIOWrapper(z.open(name), "latin-1") if name else None


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: parse_adv_bulk.py <adv_part1.zip>")
    crds = our_crds()
    print(f"delivered firms with a CRD: {len(crds)}")
    z = zipfile.ZipFile(sys.argv[1])

    # 1) latest base filing per CRD (Item 5.F AUM + FilingID)
    base = {}
    f = _open(z, "IA_ADV_Base_A")
    rd = csv.reader(f)
    H = {c.strip('"'): i for i, c in enumerate(next(rd))}
    def g(row, col):
        i = H.get(col)
        return row[i].strip('"') if i is not None and i < len(row) else ""
    for row in rd:
        crd = g(row, "1E1")
        if crd not in crds:
            continue
        ds = g(row, "DateSubmitted")
        if crd not in base or ds > base[crd]["ds"]:
            base[crd] = {"ds": ds, "filingid": g(row, "FilingID"),
                         "aum": g(row, "5F2c"), "name": g(row, "1C-Legal")}
    print(f"matched in IA base: {len(base)}")

    # 2) Schedule A control person (owner/executive) per matched filing
    fid2crd = {v["filingid"]: c for c, v in base.items() if v["filingid"]}
    owners: dict = {}
    fs = _open(z, "IA_Schedule_A_B")
    rd = csv.reader(fs)
    H = {c.strip('"'): i for i, c in enumerate(next(rd))}
    for row in rd:
        crd = fid2crd.get(g(row, "FilingID"))
        if not crd:
            continue
        owners.setdefault(crd, []).append({
            "name": g(row, "Full Legal Name"), "title": g(row, "Title or Status"),
            "own": g(row, "Ownership Code"), "ctrl": g(row, "Control Person"),
            "type": g(row, "DE/FE/I")})

    def principal(ows):
        inds = [o for o in ows if o["type"] == "I"]
        pool = [o for o in inds if o["ctrl"].upper() == "Y"] or inds
        pool.sort(key=lambda o: _OWN_RANK.get(o["own"].upper(), 0), reverse=True)
        return pool[0] if pool else None

    # 3) build the fresh lookup
    out = {}
    for crd, v in base.items():
        yr = _year(v["ds"])
        if yr < FRESH_FROM_YEAR:
            continue
        rec = {"legal_name": v["name"], "filing_year": yr,
               "source": "SEC Form ADV Item 5.F (total AUM) / Schedule A (control person)"}
        aum = v["aum"].strip()
        if aum.isdigit() and aum != "0":
            rec["aum_usd"] = int(aum)
        p = principal(owners.get(crd, []))
        if p and p["name"]:
            rec["principal_name"] = _fmt_name(p["name"])
            rec["principal_title"] = (p["title"] or "").title()
        if "aum_usd" in rec or "principal_name" in rec:
            out[crd] = rec

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT} with {len(out)} firms (fresh >= {FRESH_FROM_YEAR})")


if __name__ == "__main__":
    main()
