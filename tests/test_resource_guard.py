"""Release-gate P0: resource + thread-safety guard on the operating cycle.

The engine must refuse (never silently truncate) a cycle whose input already
exceeds the declared resource budget, and must refuse a result whose threaded
state would overflow. A process-wide CycleLock guarantees one cycle per process.
"""

from __future__ import annotations

import threading

import pytest

from fointel.operate.engine import run_operating_cycle
from fointel.operate.guard import CycleLock, ResourceGuard, ResourceLimitError

EMPTY_INPUTS = {"sources": [], "per_source_limit": 0}


def test_guard_accepts_small_state() -> None:
    ResourceGuard(max_items=1000, max_state_bytes=1_000_000).check(
        {"candidates": [{"id": i} for i in range(10)]})


def test_guard_refuses_oversized_channel() -> None:
    rg = ResourceGuard(max_items=5, max_state_bytes=1_000_000)
    with pytest.raises(ResourceLimitError):
        rg.check({"candidates": [{"id": i} for i in range(10)]})


def test_guard_refuses_unserialisable_state() -> None:
    rg = ResourceGuard(max_items=1000, max_state_bytes=64)
    with pytest.raises(ResourceLimitError):
        rg.check({"candidates": [{"id": i} for i in range(50)]})


def test_engine_refuses_oversized_input_at_gate() -> None:
    # a cycle whose input candidate pool already exceeds the budget must NOT start
    big = {"sources": [], "per_source_limit": 0,
           "state": {"candidates": [{"id": i} for i in range(3_000_000)]}}
    with pytest.raises(ResourceLimitError):
        run_operating_cycle(big, engine="langgraph")


def test_empty_cycle_passes_guard() -> None:
    out = run_operating_cycle(dict(EMPTY_INPUTS), engine="langgraph")
    assert out["engine"] == "langgraph"
    assert out["state"].get("candidates", []) == []


def test_cycle_lock_excludes_concurrent_run() -> None:
    lock = CycleLock(timeout=0.2)
    assert lock.acquire() is True            # we hold the process-wide cycle lock
    with pytest.raises(ResourceLimitError):  # a second cycle must be refused
        lock.acquire(block=True)
    lock.release()

    # after release the loop is runnable again
    assert lock.acquire(block=False) is True
    lock.release()