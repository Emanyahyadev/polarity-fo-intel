# SafetyGuardrails — the hard operating rules

Architecture decision record: **ADR-005**.

These are the non-negotiable boundaries of the autonomous operating system.
They bind the operator and the code equally. If any guardrail is ambiguous, the
safe reading wins (fail closed).

## G1 — Prove before you release (never a fabrication, never a bare guess)
- No candidate is invented to make a window look productive. Empty-window
  no-ops are the default success.
- Nothing in the production dataset is promoted from a claim the verification
  standard (config/inclusion_standard.md) cannot defend under sampling.

## G2 — Authority lives in the Policy Engine, alone
- Anyone proposing an action consults `PolicyEngine.decide()` **before** acting.
- Whatever is not explicitly Tier-1 is escalated; whatever is on the Tier-3
  `never` list is refused. Never bypass.

## G3 — Fail closed on escalations
- On refuse/escalate the `graph` routes to END: the employee is never run.
  Control never continues past an action the engine has not approved.

## G4 — The resource guards are the outermost box
- `ResourceGuard` (list-channel item caps + serialized-state bytes) and
  `CycleLock` (concurrency) are enforced at the entry gate of every cycle and
  wrap both engines. A budget overrun refuses the cycle; it never truncates.

## G5 — Oracle: the human seat for judgment
- Anything that needs Eman's judgment goes to the `HumanReviewQueue`. It waits,
  does not get auto-printed, and is resolved explicitly.

## G6 — Honest labels over convenient ones
- SFO/MFO/Undetermined are assigned honestly; we never inflate counts by
  relabeling. A firm that a rule says to escalate or refuse is never silently
  released.

## G7 — Safety of the repository
- A run's decisions and results are written to a JSONL trace; a partial or
  corrupt trace is never committed as a good run. Recovery (§1) clears it.

## G8 — The default is the safe engine and rollback is immediate
- `FOINTEL_ENGINE=langgraph` is the default; `orchestrator` is the instant
  rollback path with the same employees / policy engine / trace.

Related: [Operations](Operations.md) · [RiskRegister](RiskRegister.md) ·
[Runbook](Runbook.md) · [Recovery](Recovery.md) · [RunbookMaintenance](RunbookMaintenance.md).