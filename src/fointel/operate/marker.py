"""Cross-process operating-window overlap guard.

GitHub Actions concurrency prevents CONCURRENT jobs, but a queued next window
would still start once the current one finishes — while a long run is in flight
we must not start another cycle at all (production policy: non-overlapping
windows, skip an active window, never queue a backlog).

The guard is a heartbeat marker file (not a lock over the network): whichever
process first creates it owns the operating floor; a second process that finds
a FRESH marker skips its window (records skip_overlap, exits clean). A STALE
marker (no heartbeat within `stale_after_seconds`, e.g. a dead runner) is taken
over, so a crashed cycle can never block the next window forever.

Framework-independent, config-free: this is an orchestration concern at the
same level as operate.guard.CycleLock (which protects one process; the marker
protects all processes).
"""

from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path
from typing import Optional


class CycleMarker:
    """Heartbeat marker guarding a shared operating floor (one active window).

    Owns the floor while the owning process heartbeats it; the heartbeat keeps
    the marker fresh for arbitrarily long legitimate runs. `try_acquire` is the
    single gate every operating entrypoint (cycle / continuous / backfill) goes
    through — an active window of ANY mode blocks all other modes.
    """

    def __init__(self, path: str | Path, stale_after_seconds: float = 300.0,
                 now: Optional[float] = None) -> None:
        self.path = Path(path)
        self.stale_after = float(stale_after_seconds)
        self._now = now or time.time
        self._run_id: Optional[str] = None

    # ------------------------------------------------------------------ #
    def _read(self) -> Optional[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _write(self, run_id: str, mode: str) -> None:
        payload = {
            "run_id": run_id,
            "mode": mode,
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "started_at": _iso(self._now()),
            "heartbeat_at": _iso(self._now()),
        }
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, json.dumps(payload).encode("utf-8"))
        finally:
            os.close(fd)

    def try_acquire(self, run_id: str, mode: str = "cycle") -> tuple[bool, str]:
        """Attempt to take the operating floor.

        Returns (True, reason) when acquired (reason may note a stale takeover);
        (False, reason) when a FRESH marker holds the floor and this window must
        SKIP (never queue, never duplicate)."""
        self._run_id = run_id
        holder = self._read()
        now = self._now()
        if holder is not None:
            try:
                hb = _epoch(holder.get("heartbeat_at"))
            except (TypeError, ValueError):
                hb = 0.0
            if hb and now - hb < self.stale_after:
                return (False,
                        f"operating floor held by run {holder.get('run_id')} "
                        f"({holder.get('mode')}, pid {holder.get('pid')}); "
                        "this window is SKIPPED (overlap guard)")
            # stale holder: a dead/evicted process — take over, never block forever
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        try:
            self._write(run_id, mode)
        except FileExistsError:
            older = self._read()
            return (False, f"overlap race: floor was taken by {older and older.get('run_id')}")
        return (True, "floor acquired") if holder is None else \
            (True, f"stale marker ({holder.get('run_id')}) taken over")

    def heartbeat(self) -> None:
        """Refresh the marker so a legitimately long run is never judged stale."""
        if not self._run_id:
            return
        holder = self._read()
        if not holder or holder.get("run_id") != self._run_id:
            return  # the floor is not (no longer) ours — do not touch it
        payload = {**holder, "heartbeat_at": _iso(self._now())}
        try:
            self.path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass  # a lost race to a takeover is decided by try_acquire, not here

    def release(self) -> None:
        """Release the floor (only if it is still ours)."""
        holder = self._read()
        if holder and holder.get("run_id") == self._run_id:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        self._run_id = None


def _iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _epoch(iso: str) -> float:
    from datetime import datetime
    return datetime.fromisoformat(iso).timestamp()