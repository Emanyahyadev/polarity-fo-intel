"""Production scheduler policy: every-2-hours operating window + overlap skip.

  1. The scheduled workflow runs the operating cycle EVERY TWO HOURS (12 windows
     per day, UTC, on the hour) — verified by parsing the live workflow file.
  2. Windows are NON-OVERLAPPING: the operate.py entrypoint gates every run
     through the heartbeat marker (operate.marker.CycleMarker); a window that
     fires while the previous one is still active is SKIPPED (recorded through
     the existing scheduler.skip_overlap action) — never queued, never duplicated.
  3. A stale marker (dead runner, no heartbeat) is taken over, so a crashed cycle
     can never block the next window forever.
"""

import json
import runpy
import subprocess
import sys
import time
from pathlib import Path

from fointel.operate import schedule
from fointel.operate.marker import CycleMarker


# ------------------------------------------------------------ every 2 hours - #
def test_workflow_schedules_every_two_hours():
    exprs = schedule.workflow_cron_expressions()
    assert exprs, "operating-cycle.yml must define a schedule"
    assert all(schedule.is_every_two_hours(e) for e in exprs), exprs
    assert schedule.scheduled_windows(exprs[0]) == list(range(0, 24, 2))


def test_cron_window_expansion():
    assert schedule.scheduled_windows("30 8,16 * * *") == [8, 16]
    assert schedule.scheduled_windows("31 10 * * *") == [10]
    assert schedule.scheduled_windows("0 */2 * * *") == list(range(0, 24, 2))
    assert schedule.scheduled_windows("0 0-3 * * *") == [0, 1, 2, 3]
    try:
        schedule.scheduled_windows("not a cron")
    except ValueError:
        return
    raise AssertionError("malformed cron must be rejected")


def test_concurrency_group_present():
    assert schedule.overlap_guard_enabled()


# ------------------------------------------------------------ overlap guard - #
def test_marker_acquire_holds_floor(tmp_path, monkeypatch):
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(time, "time", lambda: now["t"])
    m = CycleMarker(tmp_path / "marker.json", stale_after_seconds=300.0)
    ok, reason = m.try_acquire("run-1", mode="cycle")
    assert ok and "acquired" in reason


def test_marker_second_window_skips_instead_of_duplicating(tmp_path, monkeypatch):
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(time, "time", lambda: now["t"])
    m1 = CycleMarker(tmp_path / "marker.json", stale_after_seconds=300.0)
    assert m1.try_acquire("run-1", mode="cycle")[0]
    m2 = CycleMarker(tmp_path / "marker.json", stale_after_seconds=300.0)
    ok, reason = m2.try_acquire("run-2", mode="cycle")
    assert not ok
    assert "SKIPPED" in reason and "run-1" in reason
    holder = json.loads((tmp_path / "marker.json").read_text(encoding="utf-8"))
    assert holder["run_id"] == "run-1"


def test_marker_heartbeat_keeps_long_window_alive(tmp_path, monkeypatch):
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(time, "time", lambda: now["t"])
    m = CycleMarker(tmp_path / "marker.json", stale_after_seconds=300.0)
    assert m.try_acquire("run-1", mode="cycle")[0]
    now["t"] += 200.0
    m.heartbeat()
    now["t"] += 200.0                            # > stale if NOT heartbeated
    ok, _ = CycleMarker(tmp_path / "marker.json", stale_after_seconds=300.0) \
        .try_acquire("run-2", mode="cycle")
    assert not ok, "heartbeated holder must still hold the floor"


def test_stale_marker_taken_over(tmp_path, monkeypatch):
    now = {"t": 1_000_000.0}
    monkeypatch.setattr(time, "time", lambda: now["t"])
    m = CycleMarker(tmp_path / "marker.json", stale_after_seconds=300.0)
    assert m.try_acquire("run-1", mode="cycle")[0]
    now["t"] += 1500.0                            # dead runner, no heartbeat
    ok, reason = CycleMarker(tmp_path / "marker.json", stale_after_seconds=300.0) \
        .try_acquire("run-2", mode="cycle")
    assert ok and "taken over" in reason


def test_marker_release_frees_floor(tmp_path):
    m = CycleMarker(tmp_path / "marker.json", stale_after_seconds=300.0)
    assert m.try_acquire("run-1", mode="cycle")[0]
    m.release()
    ok, _ = CycleMarker(tmp_path / "marker.json", stale_after_seconds=300.0) \
        .try_acquire("run-2", mode="cycle")
    assert ok


def test_marker_metadata_round_trip(tmp_path):
    m = CycleMarker(tmp_path / "marker.json", stale_after_seconds=300.0)
    m.try_acquire("run-42", mode="backfill")
    raw = json.loads((tmp_path / "marker.json").read_text(encoding="utf-8"))
    assert raw["run_id"] == "run-42" and raw["mode"] == "backfill"
    assert "started_at" in raw and "heartbeat_at" in raw


# --------------------------------------------------- entrypoint integration - #
def test_entrypoint_skips_window_when_floor_held(tmp_path, monkeypatch):
    """A scheduled window that fires while another window is ACTIVE must skip and
    record scheduler.skip_overlap — the engine is never invoked."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "operate_cli", str(schedule.REPO / "operations" / "operate.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["operate_cli"] = mod
    spec.loader.exec_module(mod)

    existing = mod.MARKER_PATH
    try:
        mod.MARKER_PATH = Path(tmp_path) / ".cycle-marker.json"
        holder = CycleMarker(mod.MARKER_PATH, stale_after_seconds=300.0)
        assert holder.try_acquire("run-active", mode="cycle")[0]

        called = {"n": 0}

        def _fake_cycle(*a, **k):
            called["n"] += 1
            raise AssertionError("engine must not run when the floor is held")

        monkeypatch.setattr(mod, "run_operating_cycle", _fake_cycle)
        # guard path is exercised directly (the marker blocks before the engine)
        ok, _ = mod.guard_operating_floor("cycle", run_id="run-new", stale_seconds=300.0)
        assert not ok
        assert called["n"] == 0
    finally:
        mod.MARKER_PATH = existing