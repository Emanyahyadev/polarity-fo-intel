# Runbook — operational procedures for a human

This is the operator's source of truth for *what to do*. It pairs with
[Operations](Operations.md) (the model), [Monitoring](Monitoring.md) (the
signals), [Recovery](Recovery.md) (restoring a broken system), and
[RunbookMaintenance](RunbookMaintenance.md) (keeping the book true).

Run every command from the repo root.

## 1. Normal operation — run a cycle

```powershell
# Simulated (quiet window; exercises every stage; no network discovery)
python operations/operate.py --simulate

# With a specific engine
FOINTEL_ENGINE=orchestrator python operations/operate.py --simulate
```

Read the printed block:
- `summary` — what each stage did.
- `engine` — which executor ran.
- `trace` — the path to the JSONL run trace.
- `pending_review` — anything queued for a human seat.

## 2. Wait for a scheduled run

The operating cycle is scheduled via GitHub Actions `operating-cycle.yml`. It
regenerates `notes/*` after each run. Verify a schedule landed:

```
git pull
git log --oneline -3
python scripts/generate_history.py
```

## 3. Review pending judgments

Anything on the `HumanReviewQueue` needs Eman's seat. `operate.py` prints it;
queue items carry `id`, `reason`, `suggested_action`. Resolve each with an
explicit decision (approve / reject), record it, and re-run the cycle so the
decision is threaded into the next window.

## 4. Regenerate the history artifacts

```bash
python scripts/generate_history.py
```

This regenerates `notes/{run,build,session}_history.md` so the observable trail
stays in git.

## 5. Run the test gate (do this after any change)

```bash
python -m pytest
```

The `test-gate.yml` workflow runs this on push/PR. Nothing ships before it
passes.

## 6. Switch the engine (rollback procedure)

```bash
# To the legacy deterministic loop:
FOINTEL_ENGINE=orchestrator python operations/operate.py --simulate

# Back to LangGraph (default):
python operations/operate.py --simulate
```

The env var is the rollback — no code change required. See ADR-004.

## 7. Recover from a stuck cycle

If a cycle fails to acquire the cycle lock, it refuses with a
`ResourceLimitError`. Wait for the lock to free, then retry. If the lock stays
held, kill the stuck process and retry. Full procedure in [Recovery](Recovery.md).

## 8. Audit a trace after an unexpected event

```
ls logs/operating/run-<ts>-<id>.jsonl
```

Search the trace for the failing agent/action, read the `decision.reason`, and
check the matching summary for escalation count.

Related: [Recovery](Recovery.md) · [Monitoring](Monitoring.md) ·
[RiskRegister](RiskRegister.md) · [RunbookMaintenance](RunbookMaintenance.md).