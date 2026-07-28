"""
Release-integrity tests — the anti-drift guard.

These bind the DELIVERED artifacts (canonical store, CSV, xlsx, stats report) to each
other and to the always-true rules, so a future change that repairs the data but forgets
to regenerate a derived file (the exact defect that produced stale "50 records / 13/13"
docs) fails CI instead of shipping. Also enforces Rule 1 (real per-cell provenance, no
reconstruct) and Rule 2 (evidence-backed classification) natively.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

from fointel.rag.load import load_records_from_store, DEFAULT_STORE, DEFAULT_CSV

# Resolve delivered artifacts from the repo root (NOT the cwd), so running pytest from a
# subdirectory cannot make STORE.exists() falsely False and silently skip the whole suite.
ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / DEFAULT_STORE
pytestmark = pytest.mark.skipif(not STORE.exists(), reason="no delivered store")


@pytest.fixture(scope="module")
def records():
    return load_records_from_store(str(STORE))


def test_store_csv_stats_counts_agree(records):
    """The delivered count must be identical across store, CSV, and the stats report —
    no derived artifact left behind."""
    n = len(records)
    csv_rows = list(csv.DictReader((ROOT / DEFAULT_CSV).read_text(encoding="utf-8").splitlines()))
    assert len(csv_rows) == n, "CSV row count != store"
    stats = json.loads((ROOT / "docs/evidence/dataset_stats.json").read_text(encoding="utf-8"))
    assert stats["n"] == n, "dataset_stats.json N != store"
    # type mix in the stats report must match the store
    from collections import Counter
    assert stats["type"] == dict(Counter(r.fo_type.value for r in records))


def test_rule1_real_provenance_native(records):
    """Rule 1: every populated high-value cell carries provenance WITH a resolvable
    source_url — proven natively on the store, no reconstruct()."""
    for r in records:
        assert not r.provenance_violations(), f"{r.name}: {r.provenance_violations()}"
    cells = [(r.name, f) for r in records for f, p in r.provenance.items() if not p.source_url]
    assert not cells, f"provenance cells missing source_url: {cells[:5]}"


def test_rule2_every_record_qualifies_and_sfo_has_single_family_evidence(records):
    """Rule 2: affirmative family-office evidence for every record; and an SFO must be a
    genuine single family — its evidence may not say the type was 'not established' nor
    mention plural 'families'/'clients'/regulatory (client) AUM."""
    for r in records:
        assert r.qualifies(), f"{r.name}: no fo_type_evidence"
    for r in records:
        if r.fo_type.value == "Single-Family Office":
            ev = (r.fo_type_evidence or "").lower()
            assert "not established" not in ev, f"{r.name}: SFO with 'not established' evidence"
            assert "regulatory aum" not in (r.estimated_aum or "").lower(), \
                f"{r.name}: SFO reporting regulatory (client) AUM"


def test_no_populated_could_not_verify(records):
    for r in records:
        bad = [f for f in r.could_not_verify if getattr(r, f, None)]
        assert not bad, f"{r.name}: populated + could_not_verify {bad}"


def test_no_duplicate_entities(records):
    ids = [r.fo_id for r in records]
    names = [r.name.upper().strip() for r in records]
    doms = [urlparse(r.website).netloc.replace("www.", "").lower() for r in records if r.website]
    assert len(ids) == len(set(ids)), "duplicate fo_id"
    assert len(names) == len(set(names)), "duplicate name"
    assert len(doms) == len(set(doms)), "duplicate website domain"


def test_key_docs_have_no_known_stale_numbers(records):
    """Anti-drift for PROSE (not just machine artifacts): the hand-written headline docs must
    not carry a number a fresh eval/run would contradict. Guards the exact regression that
    shipped 'stale 50 records / 13/13' earlier."""
    n = str(len(records))
    stale = ["13/13", "recall 0.44", "recall of 0.44", "recall: 0.44", "FN-rate 0.56",
             "9 false negative", '"records": 50', "'records': 50", "records\":50"]
    docs = ["README.md", "docs/Validation.md", "docs/KnownLimitations.md",
            "docs/evidence/README.md", "docs/ReleaseNotes.md"]
    for d in docs:
        p = ROOT / d
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for s in stale:
            assert s not in text, f"{d}: stale token {s!r}"
    assert n in (ROOT / "README.md").read_text(encoding="utf-8"), "README omits the current record count"


def test_audit_trail_nonempty_and_consistent(records):
    """Findings govern releases: the delivered xlsx must ship a non-empty Audit sheet whose
    rows reference real records."""
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(str(ROOT / "data/final/family_offices.xlsx"), read_only=True)
    au = wb["Audit"]
    rows = list(au.iter_rows(min_row=2, values_only=True))
    assert rows, "Audit sheet is empty — findings-govern-releases unproven"
    ids = {r.fo_id for r in records}
    for row in rows:
        assert row[0] in ids, f"audit row references unknown fo_id {row[0]}"
