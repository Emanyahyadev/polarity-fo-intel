# RunbookMaintenance — keeping this operating documentation true

A runbook that is not kept true is a liability. This is the discipline that
keeps the operational docs aligned with the code they describe, so a fresh
operator never executes a stale instruction.

Architecture decision record: **ADR-005**.

## Ownership & cadence
- The docs under `docs/operations/` are maintained **as part of the change
  that touches the system**, never as a separate chore.
- After any change to `operations/` or `src/fointel/operate/`, the check is:
  do `Operations`, `Monitoring`, `Runbook`, `Recovery`, `RiskRegister` still
  describe reality? If not, update them in the **same commit**.

## What must stay true
- `Operations.md` — the step list, engine switch, guard semantics, entry points.
- `Monitoring.md` — the signals and how to read them (metrics must exist in code).
- `Runbook.md` — the exact commands; verify a command before writing it.
- `Recovery.md` — timeline, recovery steps, checklist (test the steps, not just
  write them).
- `RiskRegister.md` — risks + mitigations that map to real guards/policies.

## Change gate
For any of the following, updating the relevant operation doc is **mandatory**,
not optional:
1. A new employee / step added to the cycle (`ROLE_ORDER`).
2. A new engine surface; `FOINTEL_ENGINE` behavior change.
3. A guard/policy behavior change.
4. A recovery/rollback path change.
5. A monitoring/metric or artifact path change.

## Truth check
1. Read the relevant `operations/*.md` and walk the code it references.
2. Confirm each referenced symbol exists (`graph.py::ROLE_ORDER`, `guard.py`,
   `engine.py`, `policy_engine.py`, `checkpoint.py`).
3. Confirm every command in `Runbook.md` is copy-paste correct from repo root.
4. Walk a recovery step in dry-run before writing it as a "procedure".

## Meta
- This file itself is our own scope. If an operating doc is missing, add the
  missing doc, then update this one's list. The set is: Operations, Monitoring,
  Runbook, Recovery, RiskRegister, RunbookMaintenance, SafetyGuardrails.

Related: [Operations](Operations.md) · [Monitoring](Monitoring.md) ·
[Runbook](Runbook.md) · [Recovery](Recovery.md) · [RiskRegister](RiskRegister.md) ·
[SafetyGuardrails](SafetyGuardrails.md).