"""Checkpointed catch-up acquisition (backfill) — the release-target operating mode.

Runs repeated autonomous operating cycles until one of the stop conditions:

  * TARGET   — the canonical store holds >= `target` GATE-PASSING records
               (ReleaseGate().evaluate(...).passed). Rows that merely exist
               are never counted; nothing is counted twice (dedupe by fo_id).
  * DEADLINE — the configured wall-clock (ISO, UTC) is reached.
  * SAFETY   — too many consecutive fatal cycle failures.

Progress is checkpointed under the backfill directory (default
data/backfill/), so a killed/resumed job continues from where it stopped; the
live progress JSON mirrors the checkpoint for monitoring. A final report is
written with honest numbers: rows vs gate-passing, delta over the run, and the
no-fabrication assertion (gate-passing <= rows).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

DEFAULT_SAFETY_LIMIT = 3
STATUSES = ("running", "target", "deadline", "safety", "error")


@dataclass
class CycleNote:
    at: str
    rows: int
    gate_passing: int
    new_gate_passing: int
    fatal: bool
    detail: str = ""


@dataclass
class BackfillCheckpoint:
    run_id: str
    started_at: str
    target: int
    deadline: str
    safety_limit: int
    rows: int = 0
    gate_passing: int = 0
    total_cycles: int = 0
    consecutive_failures: int = 0
    status: str = "running"
    detail: str = ""
    cycles: list[CycleNote] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BackfillCheckpoint":
        data = dict(data)
        data["cycles"] = [CycleNote(**c) for c in data.get("cycles", [])]
        return cls(**data)


class BackfillRunner:
    def __init__(
        self,
        target: int,
        deadline: str,
        *,
        run_id: str | None = None,
        safety_limit: int = DEFAULT_SAFETY_LIMIT,
        state_dir: Path | None = None,
        cycle_fn: Callable[[], dict] | None = None,
        store_records_fn: Callable[[], list] | None = None,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self.target = int(target)
        self.deadline = _parse_deadline(deadline)
        self.safety_limit = int(safety_limit)
        self.state_dir = Path(state_dir or DEFAULT_STATE_DIR)
        self.checkpoint_path = self.state_dir / "checkpoint.json"
        self.progress_path = self.state_dir / "progress.json"
        self.cycle_fn = cycle_fn
        self.store_records_fn = store_records_fn
        self.now_fn = now_fn or (lambda: datetime.now(timezone.utc))
        self.run_id = run_id or _run_id()
        self._checkpoint: BackfillCheckpoint | None = None

    # ---------------------------------------------------------- persistence - #
    def resume(self) -> BackfillCheckpoint:
        if self.checkpoint_path.is_file():
            cp = BackfillCheckpoint.from_dict(
                json.loads(self.checkpoint_path.read_text("utf-8")))
            self._checkpoint = cp
            return cp
        started = self.now_fn().isoformat()
        cp = BackfillCheckpoint(
            run_id=self.run_id, started_at=started,
            target=self.target, deadline=self.deadline.isoformat(),
            safety_limit=self.safety_limit)
        self._checkpoint = cp
        self._persist()
        return cp

    def _persist(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._checkpoint.to_dict(), indent=2)
        self.checkpoint_path.write_text(payload, "utf-8")
        self.progress_path.write_text(payload, "utf-8")

    # ---------------------------------------------------------- stop logic - #
    def should_stop(self, cp: BackfillCheckpoint) -> tuple[bool, str]:
        if cp.gate_passing >= cp.target:
            return True, "target"
        if self.now_fn() >= self.deadline:
            return True, "deadline"
        if cp.consecutive_failures >= cp.safety_limit:
            return True, "safety"
        return False, ""

    # --------------------------------------------------------------- run - #
    def run(self) -> BackfillCheckpoint:
        cp = self.resume()
        while True:
            stop, reason = self.should_stop(cp)
            if stop:
                if not cp.cycles:
                    rows, passing = self._current_counts()
                    cp.rows = rows
                    cp.gate_passing = passing
                self._finalize(cp, reason)
                break
            try:
                summary = self.cycle_fn() if self.cycle_fn else {}
                detail = (summary or {}).get("run_id", "") or ""
                self._record_cycle(cp, fatal=False, detail=str(detail))
                if (summary or {}).get("stop"):
                    # Graceful interrupt (process kill / job timeout): leave the
                    # checkpoint RUNNING so the next invocation resumes this run.
                    self._persist()
                    break
            except Exception as exc:  # noqa: BLE001 - a broken cycle ends the run honestly
                self._record_cycle(cp, fatal=True, detail=f"{type(exc).__name__}: {exc}")
            self._persist()
        return cp

    def _finalize(self, cp: BackfillCheckpoint, reason: str) -> None:
        cp.status = reason
        if reason == "target":
            cp.detail = (f"target reached: {cp.gate_passing} gate-passing records "
                         f"(target {cp.target}) over {cp.total_cycles} cycles")
        elif reason == "deadline":
            cp.detail = (f"deadline {self.deadline.isoformat()} reached with "
                         f"{cp.gate_passing} < {cp.target} gate-passing records "
                         f"({cp.rows} rows storewide)")
        else:
            cp.detail = f"{cp.consecutive_failures} consecutive fatal cycle failures"
        self._write_report(cp)

    def _record_cycle(self, cp: BackfillCheckpoint, *, fatal: bool, detail: str) -> None:
        cp.total_cycles += 1
        previous = cp.gate_passing
        rows, passing = self._current_counts()
        cp.rows = rows
        cp.gate_passing = passing
        if fatal:
            cp.consecutive_failures += 1
        else:
            cp.consecutive_failures = 0
        cp.cycles.append(CycleNote(
            at=self.now_fn().isoformat(), rows=rows, gate_passing=passing,
            new_gate_passing=passing - previous, fatal=fatal, detail=detail))

    def _current_counts(self) -> tuple[int, int]:
        """(store rows, gate-passing records) — dedupe by fo_id, count ONLY
        records that satisfy the full release policy."""
        from fointel.validation.completeness import gate_passing_count

        records = self.store_records_fn() if self.store_records_fn else []
        unique = {r.fo_id: r for r in records}
        return len(records), gate_passing_count(list(unique.values()))

    def _write_report(self, cp: BackfillCheckpoint) -> None:
        report = {
            "run_id": cp.run_id,
            "status": cp.status,
            "detail": cp.detail,
            "target": cp.target,
            "deadline": cp.deadline,
            "started_at": cp.started_at,
            "finished_at": self.now_fn().isoformat(),
            "rows_storewide": cp.rows,
            "gate_passing": cp.gate_passing,
            "delta_gate_passing": cp.gate_passing - _initial_passing(cp),
            "total_cycles": cp.total_cycles,
            "consecutive_failures": cp.consecutive_failures,
            "cycles": [c.to_dict() if hasattr(c, "to_dict") else asdict(c)
                       for c in cp.cycles],
            "no_fabrication": {"rows": cp.rows, "gate_passing": cp.gate_passing,
                               "gate_passing_le_rows": cp.gate_passing <= cp.rows},
        }
        self.state_dir.mkdir(parents=True, exist_ok=True)
        path = self.state_dir / f"backfill-{cp.run_id}-report.json"
        path.write_text(json.dumps(report, indent=2), "utf-8")


def _initial_passing(cp: BackfillCheckpoint) -> int:
    return cp.cycles[0].gate_passing if cp.cycles else 0


def _parse_deadline(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _run_id() -> str:
    import uuid
    return f"backfill-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


DEFAULT_STATE_DIR = Path(__file__).resolve().parents[3] / "data" / "backfill"