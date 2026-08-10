"""Backfill (catch-up) acquisition — the resumable, honest release-target mode.

Contracts under test:
  * only GATE-PASSING records count toward the target; mere rows never do;
  * duplicates (same fo_id) are counted once;
  * stop conditions: target, deadline, safety limit;
  * one run() drives repeated cycles until a stop condition lands;
  * checkpoints resume a killed run (run_id preserved, progress continued);
  * a final report asserts the no-fabrication invariant (gate_passing <= rows).
"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fointel.operate.backfill import BackfillRunner
from test_completeness import _rec

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self) -> None:
        self.records: list = []

    def load(self) -> list:
        return list(self.records)

    def add(self, rec) -> None:
        self.records.append(rec)


def _find(state_dir: Path, name: str) -> dict:
    return json.loads((state_dir / name).read_text("utf-8"))


def test_only_gate_passing_records_count_toward_target(tmp_path: Path):
    store = FakeStore()
    store.records = [_rec(fo_id="fo_ok"),
                     _rec(fo_id="fo_no_geo", hq_country=None)]

    def grow():
        n = len(store.records)
        if n == 2:
            rec = _rec(fo_id="fo_no_prov")                 # G8: populated w/o provenance
            rec.website = "https://fake.example.com"
            del rec.provenance["website"]
            store.add(rec)
        elif n < 9:
            store.add(_rec(fo_id=f"fo_g{n}"))

    runner = BackfillRunner(
        target=5, deadline=(NOW + timedelta(hours=1)).isoformat(),
        state_dir=tmp_path, store_records_fn=store.load,
        cycle_fn=grow, now_fn=lambda: NOW)
    cp = runner.run()
    assert cp.gate_passing == 5            # target reached
    assert cp.rows == 7                    # 2 of the 7 rows are NOT gate-passing
    assert cp.status == "target"
    assert cp.detail
    report = _find(tmp_path, f"backfill-{cp.run_id}-report.json")
    assert report["no_fabrication"]["gate_passing_le_rows"]
    assert report["gate_passing"] <= report["rows_storewide"]


def test_duplicate_fo_id_counted_once(tmp_path: Path):
    store = FakeStore()
    for _ in range(3):
        store.add(_rec(fo_id="fo_dup"))

    def grow():
        store.add(_rec(fo_id=f"fo_g{len(store.records)}"))

    runner = BackfillRunner(
        target=3, deadline=(NOW + timedelta(hours=1)).isoformat(),
        state_dir=tmp_path, store_records_fn=store.load,
        cycle_fn=grow, now_fn=lambda: NOW)
    cp = runner.run()
    assert cp.status == "target"
    assert cp.gate_passing == 3            # the winning count (3 distinct fo_ids)
    assert cp.rows == 5                    # but 5 rows were seen storewide


def test_checkpoint_resumes_killed_run(tmp_path: Path):
    store = FakeStore()

    def grow():
        store.add(_rec(fo_id=f"fo_{len(store.records) + 1}"))
        return {"stop": True}                          # simulate process kill

    run1 = BackfillRunner(target=5, deadline=(NOW + timedelta(hours=2)).isoformat(),
                          state_dir=tmp_path, store_records_fn=store.load,
                          cycle_fn=grow, now_fn=lambda: NOW)
    cp1 = run1.run()
    first_id, cycles1 = cp1.run_id, cp1.total_cycles
    assert cycles1 == 1 and cp1.status == "running"         # killed after cycle 1
    assert "backfill-" in first_id

    def grow_full():                                    # resumed without stop signal
        store.add(_rec(fo_id=f"fo_{len(store.records) + 1}"))

    run2 = BackfillRunner(target=5, deadline=(NOW + timedelta(hours=2)).isoformat(),
                          state_dir=tmp_path, store_records_fn=store.load,
                          cycle_fn=grow_full, now_fn=lambda: NOW, run_id=first_id)
    cp2 = run2.run()
    assert cp2.run_id == first_id                            # same run resumes, not a new one
    assert cp2.status == "target"
    assert cp2.total_cycles == 5

    # a fresh invocation (new run_id) must NEVER inherit a previous run's
    # checkpoint - stale safety/failure state must not poison a new run.
    run3 = BackfillRunner(target=5, deadline=(NOW + timedelta(hours=2)).isoformat(),
                          state_dir=tmp_path, store_records_fn=store.load,
                          cycle_fn=grow_full, now_fn=lambda: NOW)
    cp3 = run3.run()
    assert cp3.run_id != first_id                            # fresh run, fresh state
    assert cp3.total_cycles == 1


def test_deadline_stops_short_but_honest(tmp_path: Path):
    store = FakeStore()
    store.records = [_rec(fo_id="fo_ok")]
    runner = BackfillRunner(
        target=500, deadline=(NOW - timedelta(minutes=1)).isoformat(),
        state_dir=tmp_path, store_records_fn=store.load,
        cycle_fn=lambda: None, now_fn=lambda: NOW)
    cp = runner.run()
    assert cp.status == "deadline"
    assert cp.total_cycles == 0                              # no cycle ever ran
    assert cp.gate_passing == 1 and cp.rows == 1             # store measured anyway
    report = _find(tmp_path, f"backfill-{cp.run_id}-report.json")
    assert report["detail"]


def test_safety_limit_stops_after_fatal_failures(tmp_path: Path):
    store = FakeStore()

    def boom():
        raise RuntimeError("discovery backend down")

    runner = BackfillRunner(
        target=500, deadline=(NOW + timedelta(hours=3)).isoformat(),
        safety_limit=3, state_dir=tmp_path, store_records_fn=store.load,
        cycle_fn=boom, now_fn=lambda: NOW)
    cp = runner.run()
    assert cp.status == "safety"
    assert cp.consecutive_failures == 3
    assert cp.gate_passing == 0                              # never fabricated
    assert cp.total_cycles == 3
    report = _find(tmp_path, f"backfill-{cp.run_id}-report.json")
    assert report["status"] == "safety"


def test_success_resets_failure_counter(tmp_path: Path):
    store = FakeStore()
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1 or calls["n"] >= 4:
            raise RuntimeError("backend down")
        store.add(_rec(fo_id=f"fo_{calls['n']}"))

    runner = BackfillRunner(
        target=500, deadline=(NOW + timedelta(hours=3)).isoformat(),
        safety_limit=3, state_dir=tmp_path, store_records_fn=store.load,
        cycle_fn=flaky, now_fn=lambda: NOW)
    cp = runner.run()
    assert cp.status == "safety"
    assert cp.total_cycles == 6          # 1 fatal, 2 ok, 3 fatal tail
    assert cp.consecutive_failures == 3
    assert cp.gate_passing == 2          # the two successful cycles' records


def test_progress_json_mirrors_checkpoint(tmp_path: Path):
    store = FakeStore()

    def grow():
        store.add(_rec(fo_id="fo_prog"))

    runner = BackfillRunner(
        target=1, deadline=(NOW + timedelta(hours=3)).isoformat(),
        state_dir=tmp_path, store_records_fn=store.load,
        cycle_fn=grow, now_fn=lambda: NOW)
    cp = runner.run()
    assert cp.status == "target"
    prog = _find(tmp_path, "progress.json")
    check = _find(tmp_path, "checkpoint.json")
    assert prog == check
    assert prog["gate_passing"] == 1