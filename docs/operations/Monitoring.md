# Monitoring — Observability of the Operating Cycle

Architecture decision record: **ADR-005**.

The operating system is only trustworthy if its own behavior is observable.
Monitoring here means **evidence, in the repository**, that a normal reader can
audit — not a closed third-party dashboard. Our monitoring is deliberately
file-and-commit based so it survives exactly as long as the repo.

## 1. What we observe

Per operating run:

- **Run trace** — `logs/operating/run-<ts>-<id>.jsonl`: one line per
  `task_done` event (agent, action, decision status, reason, result).
- **Run summary** — `logs/operating/run-<ts>-<id>-summary.json`: tasks,
  statuses, escalations, trace path.

Envelope (across runs), all **generated** — never hand-edited:

- `notes/run_history.md` — every operating run indexed from the summary files.
- `notes/build_history.md` — every build (git commit) with its date.
- `notes/session_history.md` — rolling high-level session summary.

Generate with:

```
python scripts/generate_history.py
```

The generator is invoked by CI after an operating cycle, so the history
artifacts always reconcile with what actually happened on disk.

## 2. Metrics that matter

- **Cycles green** — a run where the cycle completes and results stay within
  budget (see ResourceGuard). Tracked per-run in the summary statuses.
- **Escalation rate** — number of items queued to the `HumanReviewQueue`. A rise
  means candidates are hitting the authority matrix's escalate/refuse tiers.
- **Refuse** — hard Tier-3 denials; any spike must be inspected (a `never` rule
  firing repeatedly usually signals a bad source or a policy needing a change).
- **State budget utilisation** — how close to `max_cycle_items` /
  `max_cycle_state_bytes` a cycle runs. Approach → tune discovery limits or the
  guard caps.
- **Zero-yield window** — a discovered-but-empty pool is a *valid* outcome and
  must not be read as failure (empty-window no-ops are success). Watched, not
  alarmed.

## 3. Health signals

| Signal | Source | Meaning |
|--------|--------|---------|
| Run completed | summary `outcome` | cycle reached END |
| No escalations | summary statuses | all actions were Tier-1 |
| Pending review non-empty | `HumanReviewQueue.pending()` | a human seat holds items |
| Trace written | `trace_file` | disposable evidence exists |
| Budget under cap | guard | no runaway pool / state |

## 4. Dashboards

There is **no** production dashboards in this phase (per ADR-005, a public
runtime endpoint is NOT authorized). Instead:

- **Human review seat** — the `HumanReviewQueue` printed by `operate.py` (the
  `pending_review` block). This is the operator's natural dashboard.
- **History artifacts** — the generated `notes/*.md` ARE the dashboard-as-commit.
- **CI log** — `operating-cycle.yml` prints the summary each scheduled run.

## 5. Reaching the signal we are responsible for

1. Run `python operations/operate.py --simulate` — read the printed summary.
2. Regenerate history: `python scripts/generate_history.py` → `notes/`.
3. Diff `notes/run_history.md` against the previous commit.
4. Inspect `logs/operating/` if a run misbehaved.

Every schedule-produced run is independently verifiable by a healthy human the
same way, no special access.

## 6. Prone to silence?

If `notes/` stops being committed, or `logs/operating/` grows but the scheduler
did not run, treat it as a **silent-drift alarm** and consult
[Recovery](Recovery.md).

Related: [Runbook](Runbook.md) · [Operations](Operations.md) ·
[Recovery](Recovery.md) · [RiskRegister](RiskRegister.md) ·
[RunbookMaintenance](RunbookMaintenance.md).