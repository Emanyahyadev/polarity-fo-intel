"""Scheduler policy — every-2-hours operating window + overlap-skip semantics.

Pure helpers around the workflow file and the heartbeat marker (operate.marker),
so the scheduler policy is testable without GitHub Actions:
  * window expansion of a cron expression (the '*', '*/N', literal and comma
    forms this repo uses) — proves the scheduled windows are 12/day on the hour;
  * workflow introspection (cron expressions, concurrency group);
  * who currently holds the operating floor (marker state).
"""

from __future__ import annotations

import json
from itertools import chain
from pathlib import Path
from typing import Optional

import yaml

REPO = Path(__file__).resolve().parents[3]
WORKFLOW = REPO / ".github" / "workflows" / "operating-cycle.yml"


def _expand(token: str, span: range) -> list[int]:
    if token == "*":
        return list(span)
    if token.startswith("*/"):
        step = int(token[2:])
        return [h for h in span if h % step == 0]
    out = []
    for part in token.split(","):
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-"))
            out.extend(range(lo, hi + 1))
        else:
            out.append(int(part))
    return out


def scheduled_windows(cron: str) -> list[int]:
    """Hours of day (UTC) a 5-field cron expression schedules. Raises on malformed input."""
    fields = cron.split()
    if len(fields) != 5:
        raise ValueError(f"not a 5-field cron expression: {cron!r}")
    hours = fields[1]
    return sorted(set(chain.from_iterable(
        _expand(h, range(24)) for h in hours.split(","))))


def is_every_two_hours(expr: str) -> bool:
    """True when the expression schedules exactly 12 windows, one per 2h slot,
    on the hour (e.g. '0 */2 * * *')."""
    windows = scheduled_windows(expr)
    return len(windows) == 12 and windows == list(range(0, 24, 2))


def _workflow_on(data: dict) -> dict:
    """PyYAML parses the YAML 1.1 reserved word `on` as the boolean True."""
    trigger = data.get("on") or data.get(True) or {}
    return trigger if isinstance(trigger, dict) else {}


def workflow_cron_expressions() -> list[str]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    sched = _workflow_on(data).get("schedule") or []
    return [entry["cron"] for entry in sched]


def overlap_guard_enabled() -> bool:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    concurrency = data.get("concurrency") or {}
    return bool(concurrency.get("group"))


def active_window() -> Optional[dict]:
    """Current operating-floor holder from the heartbeat marker (None = free)."""
    try:
        return json.loads((REPO / "data" / ".cycle-marker.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None