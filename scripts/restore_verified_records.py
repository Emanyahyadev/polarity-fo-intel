"""
Restore the verified Stage-1 records that the autonomous operating cycle dropped
in 9c125e6 ("chore(data): autonomous data update ..."): the new discovery run
replaced data/final/records.json with the raw pipeline pool, deleting 10
website-verified Single-Family Offices + 2 other verified records. Source of
truth is the git-parent store blob; the restore is by fo_id and idempotent.

Run from repo root:
    az 3.12 scripts/restore_verified_records.py
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORDS = ROOT / "data" / "final" / "records.json"
KEEP_COMMIT = "9c125e6^"  # parent of the destructive autonomous-data commit


def main():
    raw = subprocess.run(["git", "show", f"{KEEP_COMMIT}:data/final/records.json"],
                         capture_output=True, text=True, cwd=ROOT,
                         check=True).stdout
    archived = json.loads(raw)
    current = json.loads(RECORDS.read_text(encoding="utf-8"))
    have = {r["fo_id"] for r in current}
    missing = [r for r in archived if r["fo_id"] not in have]
    sfo = [r for r in missing if r["fo_type"] == "Single-Family Office"]
    print(f"current store {len(current)} · archived {len(archived)} · missing {len(missing)} (SFO {len(sfo)})")
    for r in sorted(missing, key=lambda x: x["name"]):
        print(f"  + {r['fo_id']}  {r['name']}  [{r['fo_type']}]")
    if not missing:
        print("nothing to restore")
        return
    restored = current + missing
    RECORDS.write_text(json.dumps(restored, indent=2), encoding="utf-8")
    print(f"restored: wrote {len(restored)} records to data/final/records.json")


if __name__ == "__main__":
    main()