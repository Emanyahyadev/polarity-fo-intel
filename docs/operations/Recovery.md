# Recovery — restoring a broken operating system

Recovery is our discipline for a broken system: **restore a healthy state first,
diagnose second, and never re-report broken work as finished.** Each procedure
is tested and time-boxed so a normal operator can recover without fresh
architecture decisions.

Architecture decision record: **ADR-006** (recovery & rollback policy).

## Timeline discipline

- **T0 — stalemate:** a run is stuck, a lock is held, or a trace is half-written.
- **T0+15m:** the cycle lock / stuck trace is forcibly cleared.
- **T0+30m:** data is confirmed intact and a clean cycle finishes.
- **T0+60m:** the post-mortem note is written to `docs/DecisionLog.md`.

If the recovery exceeds these, escalate to a senior human rather than improvise.

## R1 — a cycle is stuck on the lock or half-written trace

Symptom: `operate.py` raises `ResourceLimitError` "cycle lock not acquired /
held by another operating run", or a trace file appears truncated.

Recovery:
1. Confirm the lock: `ResourceGuard`/`CycleLock` release on a forced restart.
2. Kill the stuck process (a single process holds the process-wide lock).
3. Delete or archive the partial trace file (it was never committed).
4. Re-run: `python operations/operate.py --simulate`.
5. Only when a clean run finishes with a summary is the lock considered clear.

## 2 — a run reported broken results

Symptom: a summary shows many refuses, or a trace shows write errors.

Recovery:
1. Open the run summary and trace; read the `decision.reason` of the failures.
2. Determine whether it is a **source problem** (retry) or a **code/policy
   problem** (fix). Do not fabricate a candidate to heal a count.
3. Fix the cause and re-run.

Empty-window no-ops are success; a zero-yield run is NOT an incident by itself.

## 3 — an engine is unstable

Symptom: the LangGraph (`langgraph`) executor misbehaves in a way that blocks
runs.

Recovery:
```
# flip the executor only:
FOINTEL_ENGINE=orchestrator python operations/operate.py --simulate
```
This restores the legacy deterministic loop (ADR-004). Same employees, same
policy engine, same trace, same review queue. This is the rollback path.

Once stable, diagnose why `langgraph` failed (check checkpointer / graph route).

## 4 — a run writes a corrupt or oversized state

Symptom: guard refuses a cycle for exceeding a list-channel item count or the
`max_cycle_state_bytes` budget.

Recovery:
1. Untag the offending state — the guard refuses at the gate, so no partial
   write occurred.
2. Reduce the offending channel (or the input source limit) and rerun.
3. If the guard is too tight for a legitimate load, tune the cap in
   `src/fointel/config.py` (and update the Risk Register).

## 5 — the history artifacts go stale

Symptom: `notes/*` no longer advance with runs, or a generated artifact disagrees
with `logs/operating/`.

Recovery:
1. Regenerate: `python scripts/generate_history.py`.
2. Diff `notes/run_history.md` against the prior commit.
3. If the scheduler missed a window, check GH Actions; rerun the operating
   cycle; recommit notes. A silent gap is a post-mortem incident, not a shrug.

## 6 — a pending review item is orphaned

Symptom: the `HumanReviewQueue` holds an item that will never be decided.

Recovery:
1. Resolve it explicitly through `resolve(...)` (approve/reject + decided_by).
2. Ensure the next cycle threads that decision.

## Checklist gate before a return to normal

- [ ] A clean cycle completes with a summary (no half-written trace).
- [ ] The engine used is known and intentional.
- [ ] History artifacts regenerated and committed.
- [ ] Any policy/payload change is documented in `docs/DecisionLog.md`.
- [ ] The test gate passes (`python -m pytest`).

Related: [Runbook](Runbook.md) · [Monitoring](Monitoring.md) ·
[RiskRegister](RiskRegister.md) · [Operations](Operations.md) ·
[RunbookMaintenance](RunbookMaintenance.md).