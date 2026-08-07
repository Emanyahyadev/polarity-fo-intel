# Operating-System PRD & RND

This covers the **operating system** (the autonomous cycle that keeps the
product current), not the product data itself (product PRD/RND live in the
product docs). Status: **Implemented (v1)**, iteration continues.

## PRD — product requirements (operating system)

### 1. Problem
The product dataset decays. There is no scheduled, autonomous, auditable loop
that refreshes it without a human running ad-hoc scripts. Manual refresh is
untraceable and does not scale.

### 2. Who it serves
- **Eman (operator/seat):** review queue, monitoring, rollback control.
- **CI:** schedules regeneration of the observable history.
- **Later:** an ops console reading the production trace + history artifacts.

### 3. Requirements traceability
| ID | Requirement | Evidence in repo |
|----|-------------|-----------------|
| PRD-1 | One command runs one full cycle | `operations/operate.py` |
| PRD-2 | Cycle is idempotent, scheduled | Repeatable; `operating-cycle.yml` cron |
| PRD-3 | Authority enforced before actions | `policy_engine.py::decide()` (ADR-003) |
| PRD-4 | Blank, no-op windows are success | `EmployeeSkip`, empty-window policy |
| PRD-5 | Every decision/result is tracked | JSONL trace + summary (ADR-005) |
| PRD-6 | Human judgments go to a queue | `HumanReviewQueue` |
| PRD-7 | Resource-bounded, concurrency-safe | `guard.py` (ResourceGuard/CycleLock) |
| PRD-8 | Engine is switchable; rollback available | `FOINTEL_ENGINE` (ADR-004) |
| PRD-9 | Checkpointed / resumable | `checkpoint.py` (ADR-004) |
| PRD-10 | Observable via committed artifacts | `scripts/generate_history.py` (ADR-005) |
| PRD-11 | Change is gated by tests | `test-gate.yml` |

### 4. Non-goals (this phase)
- Public runtime monitoring endpoint (deliberately absent; ADR-005).
- Mutable, spontaneous actions (only scheduled roles run).

### 5. Definition of done
A scheduled cycle completes, writes its trace + summary, regenerates history,
and a human can audit it with no special access.

## RND — research & development notes

### R1. How the policy gate is trusted
`decide()` is consulted in control flow (`graph._node`), not in a comment.
Actions not on the Tier-1 allow-list escalate by default — so a mis-listed
action is a *refusal*, never a silent green. Fail-closed is structural.

### R2. How the two engines stay equivalent
Both run the same `_DelegatingEmployee` array (ADR-002) over the same agent
registry, so behavior parity is not a coincidence but a shared substrate. The
LangGraph path replays its steps into the identical JSONL trace and review
queue the loop uses, so consumers see the same record regardless of engine.

### R3. Testing approach
`test-gate.yml` runs both engines + verify scripts. Tests cover guard refusal
(budgets, lock), policy tiers, engine selection/rollback, contact standard,
checkpointing, and the history generator. Core business algorithms are unit
tested outside the loop.

### R4. What we deliberately do not do
- No deeper network hooks in the box for this phase.
- No deterministic guesses: the default is a no-op or an escalation.
- No runtime dashboard, so operations reading a public state is impossible now.

## Open questions for the next cycle
- When (if ever) does an on-box monitoring endpoint become authorized? (ADR-005
  says not yet.)
- Should the human-approval pause be enabled by default on real (non-simulated)
  discovery windows, or remain opt-in? (ADR-004 keeps it OFF.)

Related: [Operations](Operations.md) · [Runbook](Runbook.md) ·
[Recovery](Recovery.md) · [Monitoring](Monitoring.md) ·
[RiskRegister](RiskRegister.md) · ADR-001…006.