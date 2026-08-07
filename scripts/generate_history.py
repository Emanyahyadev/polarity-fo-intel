"""
Generate the observability history artifacts from REAL evidence only:

    notes/run_history.md     — every operating-cycle run (from logs/operating/*.jsonl
                               + *-summary.json). No numbers are invented: each row is
                               derived from the files on disk.
    notes/build_history.md   — every build (git commit) with a short stat.
    notes/session_history.md — a rolling high-level summary of working sessions.

Run:  python scripts/generate_history.py [--runs-dir logs/operating]
This is the same generator invoked by CI after an operating cycle, so the
artifacts always reconcile with what actually happened.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTES = ROOT / "notes"
LOGS = ROOT / "logs" / "operating"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _run_summaries(runs_dir: Path) -> list[dict]:
    """Summaries are the canonical per-run record (written by Orchestrator.dump_summary)."""
    out: list[dict] = []
    if not runs_dir.is_dir():
        return out
    for sf in sorted(runs_dir.glob("*-summary.json")):
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            data["_summary_file"] = sf.name
            data["_run_id"] = sf.name.replace("-summary.json", "")
            out.append(data)
        except Exception as exc:  # noqa: BLE001 — a corrupt file must not sink the report
            out.append({"_summary_file": sf.name, "_error": str(exc)})
    return out


def _git_log() -> list[str]:
    try:
        return subprocess.run(
            ["git", "log", "--pretty=%h|%ad|%s", "--date=short", "-40"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.splitlines()
    except Exception:  # noqa: BLE001 — not a git repo → empty history, not a crash
        return []


def _render_run_history(summaries: list[dict]) -> str:
    lines = [
        "# Run History", "",
        f"Generated: {_now()}  ·  source: `logs/operating/*-summary.json` (never hand-edited).",
        "",
        f"**{len(summaries)} operating-cycle run(s)** indexed.", "",
        "| Run | Tasks | Statuses | Escalated | Trace |",
        "|---|---|---|---|---|",
    ]
    for s in summaries:
        statuses = s.get("statuses", {})
        row = (
            f"| `{s.get('_run_id', '?')}` | {s.get('tasks', '-')} | "
            f"{statuses or '-'} | {s.get('escalated_to_human_review', '-')} | "
            f"{s.get('trace_file', s.get('_summary_file', '-'))} |"
        )
        lines.append(row)
    if not summaries:
        lines.append("_(no summary files yet — run `operations/operate.py --simulate`)_")
    return "\n".join(lines) + "\n"


def _render_build_history() -> str:
    lines = ["# Build History", "", f"Generated: {_now()}  ·  source: `git log`.", ""]
    commits = _git_log()
    if not commits:
        lines.append("_(no git history — run in a clone with commits)_")
        return "\n".join(lines) + "\n"
    lines.append(f"**{len(commits)} commits** in the current `main` view.")
    lines.append("")
    lines.append("| Commit | Date | Summary |")
    lines.append("|---|---|---|")
    for c in commits:
        h, date, msg = c.split("|", 2)
        lines.append(f"| `{h}` | {date} | {msg} |")
    return "\n".join(lines) + "\n"


def _iso_day(run_day: str) -> str:
    """'20260807' (run-id timestamp form) -> '2026-08-07' (ISO, matches git dates)."""
    if len(run_day) == 8 and run_day.isdigit():
        return f"{run_day[:4]}-{run_day[4:6]}-{run_day[6:]}"
    return run_day


def _render_session_history(summaries: list[dict], builds: list[str]) -> str:
    # A session = a distinct wall-clock block; we approximate from run dates + build days.
    run_days = sorted({_iso_day(s.get("_run_id", "").split("T")[0].removeprefix("run-"))
                       for s in summaries})
    build_days = sorted({c.split("|")[1] for c in builds})
    lines = [
        "# Session History", "",
        f"Generated: {_now()}. Derived from run timestamps and build dates — no "
        "hand-entered hours.", "",
        "**Active operating days:** " + (", ".join(run_days) if run_days else "none") + "",
        "**Build (commit) days:** " + (", ".join(build_days) if build_days else "none") + "",
        "",
        "## Sessions",
    ]
    for day in sorted(set(run_days) | set(build_days)):
        n_runs = sum(1 for s in summaries
                     if _iso_day(s.get("_run_id", "").split("T")[0].removeprefix("run-")) == day)
        n_builds = sum(1 for c in builds if c.split("|")[1] == day)
        lines.append(f"- **{day}** — {n_runs} operating run(s), {n_builds} build(s)")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate observability history artifacts")
    ap.add_argument("--runs-dir", type=Path, default=LOGS, help="logs/operating dir")
    args = ap.parse_args()

    NOTES.mkdir(parents=True, exist_ok=True)
    summaries = _run_summaries(args.runs_dir)
    builds = _git_log()

    (NOTES / "run_history.md").write_text(_render_run_history(summaries), encoding="utf-8")
    (NOTES / "build_history.md").write_text(_render_build_history(), encoding="utf-8")
    (NOTES / "session_history.md").write_text(
        _render_session_history(summaries, builds), encoding="utf-8")

    print(f"run_history.md:     {len(summaries)} runs indexed")
    print(f"build_history.md:   {len(builds)} builds indexed")
    print(f"session_history.md: written")


if __name__ == "__main__":
    main()