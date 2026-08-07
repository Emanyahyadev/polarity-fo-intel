# Risk Register — operating-system risks

Operation-specific risks for the **autonomous operating system**. Product/data
risks live in the product [Risk Register / KnownLimitations](KnownLimitations.md)
and [Tradeoffs](Tradeoffs.md). This register is about the machinery that keeps
the product current.

Architecture decision record: **ADR-005** (safety and recovery).

Severity: **H** high / **M** medium / **L** low. Likelihood: **H/M/L**.

## R1 — Scheduler overlap (concurrent cycles) — H / L
**Risk:** two scheduler fires (retried cron + manual run) run against the same
repository/trace, corrupting a trace or duplicating writes.
**Mitigation:** the `CycleLock` is acquired at the outermost gate
(`engine.py:65`); the second caller is refused with `ResourceLimitError`.
**Residual:** very low; retry logic can mask the refusal. Update [Recovery §1](Recovery.md).

## R2 — Runaway candidate pool / oversized threaded state — H / L
**Risk:** a discovery spike grows an unbounded pool or an oversized cycle state,
exhausting the process or blowing the checkpoint.
**Mitigation:** `ResourceGuard` refuses any cycle whose list channels or
serialized size exceed the caps **before** work. No partial write.
**Residual:** guard tuned too tight rejects legitimate load. Track budget
utilisation (Monitoring).

## R3 — Engine regression (LangGraph change breaks a run) — M / M
**Risk:** an executor change silently changes run behavior.
**Mitigation:** dual-executor with `FOINTEL_ENGINE`; rollback to a fixed state.
Both engines share Policy Engine / trace / review queue. A/B-equivalent
contract (default OFF for new surfaces) preserves parity.
**Residual:** the rollback is manual, so it depends on an operator noticing.
Depends on monitoring.

## R4 — Policy gap leads to an unapproved action — M / L
**Risk:** an action not in the authority matrix runs freely.
**Mitigation:** the Policy Engine **escalates by default** when a proposed action
is not explicitly Tier-1; `graph.py` routes refuse/escalate to END (employee
is never run). Nothing bypasses the engine.

## R5 — Stale / missing scheduler → silent drift — M / L
**Risk:** the build is silent; nothing runs; `notes/` stops advancing.
**Mitigation:** observability artifacts are part of CI; staleness in `notes/`
is a monitoring signal (see [Monitoring §6](Monitoring.md)).
**Residual:** needs a human to notice; that is our cover boundary (ADR-005).

## R6 — A single failing source sinks a cycle — M / L
**Risk:** discovery/de lookup on one bad source aborts the whole run.
**Mitigation:** DiscoveryEmployee degrades a failed source to a logged gap /
zero-yield is normal, instead of failing the cycle.

## R7 — Step that fabricates rather than no-ops — M / L
**Risk:** an empty-window employee invents a candidate to look busy.
**Mitigation:** empty-window no-op is the defined success (`EmployeeSkip` and
empty-pool policy). "Never fabricate work on an empty pool" is in the employee
contracts and policy matrix.

## R8 — Generic mailbox promoted as a named route — M / L
**Risk:** an info@/contact@ mailbox is sold as a person's email.
**Mitigation:** `contact_review` refuses generic mailboxes and non-corporate
types in control flow; they never count as routes.

Related: [Operations](Operations.md) · [Recovery](Recovery.md) ·
[Monitoring](Monitoring.md) · [Runbook](Runbook.md) ·
[RunbookMaintenance](RunbookMaintenance.md).