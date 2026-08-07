"""
Resource + thread-safety guard (operate layer).

Orchestration concern, NOT business logic. It bounds the OUTERMOST box so a
runaway candidate pool, an oversized threaded state, or two concurrent operating
cycles can never exhaust the process or corrupt a run trace / repository.

Two duties:
  1. State budget — cap the number of items carried in any cycle list channel and
     the total serialized size of the `CycleState`. Applied by the graph BEFORE a
     node runs and by the engine before the whole cycle, so a cycle that would
     spawn an unbounded pool is refused at the gate instead of degrading silently.
  2. Concurrency confinement — a process-wide acquire (thread lock) ensures only
     one operating cycle writes a given run trace / repository at a time.

The guard is framework-independent on purpose: it lives beside the orchestrator,
not inside an AI Employee, and it does not duplicate any policy decision. It only
caps resources; the Policy Engine remains the sole authority on business actions.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Optional

from ..config import settings

# Channels on the shared cycle state that may grow without bound during a cycle.
# Anything outside this list contributes only to the serialized-size budget.
_LIST_CHANNELS = (
    "candidates",
    "resolved",
    "validated",
    "classified",
    "decisions",
    "approved",
    "quarantined",
    "escalated",
    "errors",
)


class ResourceLimitError(Exception):
    """Raised when a cycle would exceed its declared resource budget.

    The guard refuses the cycle at the outermost gate (before work) so nothing
    partial is written. Callers must catch this and record it on the trace as a
    refused/escalated action — never let it silently truncate data.
    """


def _serialized_size(state: dict[str, Any]) -> int:
    """Byte size of the state as it would be checkpointed/threaded. JSON is the
    on-the-wire form (LangGraph checkpointer + JSONL trace), so it is the honest
    measure of a budget overrun."""
    try:
        return len(json.dumps(state, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return settings.max_cycle_state_bytes + 1  # un-serialisable == over budget


class ResourceGuard:
    """Enforces the declared state/chain budget for one operating cycle."""

    def __init__(self,
                 max_items: Optional[int] = None,
                 max_state_bytes: Optional[int] = None) -> None:
        self.max_items = settings.max_cycle_items if max_items is None else max_items
        self.max_state_bytes = (
            settings.max_cycle_state_bytes if max_state_bytes is None else max_state_bytes
        )

    def check(self, state: dict[str, Any]) -> None:
        """Raise ResourceLimitError if `state` violates the list-channel or
        serialized-size budget. Called at the cycle gate (before work)."""
        for channel in _LIST_CHANNELS:
            n = len(state.get(channel) or [])
            if n > self.max_items:
                raise ResourceLimitError(
                    f"cycle state channel {channel!r} has {n} items (budget {self.max_items})"
                )
        size = _serialized_size(state or {})
        if size > self.max_state_bytes:
            raise ResourceLimitError(
                f"cycle state is {size} bytes (budget {self.max_state_bytes})"
            )


class CycleLock:
    """Process-wide mutual exclusion around an operating cycle.

    Used so two schedulers (e.g. a retried cron firing plus a manual run) cannot
    run concurrently against the same repository / trace. Idiomatic with the
    orchestrator's scheduler.retry / skip_overlap actions."
    """

    def __init__(self, timeout: Optional[float] = None) -> None:
        self._lock = threading.Lock()
        self.timeout = timeout if timeout is not None else settings.cycle_lock_timeout_seconds

    def acquire(self, block: bool = True) -> bool:
        """Acquire the cycle lock. `block=False` for a non-blocking probe."""
        if block:
            acquired = self._lock.acquire(timeout=self.timeout)
            if not acquired:
                raise ResourceLimitError(
                    f"operating cycle lock not acquired within {self.timeout}s; "
                    "another cycle is still running"
                )
            return True
        return self._lock.acquire(blocking=False)

    def release(self) -> None:
        try:
            self._lock.release()
        except RuntimeError:
            pass  # never crashed an unlock for an unexpected path


__all__ = ["ResourceGuard", "ResourceLimitError", "CycleLock"]