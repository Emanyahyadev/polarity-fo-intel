# CheckpointReport — operating system (Stage 2 layer)

This report follows the eight-block form: operating facts are measured from the
repo, what is AI-built is marked as such, and nothing is claimed as human work
that was not. ADRs: **ADR-001…006**.

## 1. Current operating facts (measured)
- **Engine:** `FOINTEL_ENGINE=langgraph` default; `orchestrator` rollback path
  exists and both pass the CI gate.
- **Cycle:** 14 employees in `ROLE_ORDER` (scheduler → engineering → discovery →
  entity → duplicate → enrichment → validation → classification → governance →
  release → embedding → freshness → monitoring → logging).
- **Traces:** `logs/operating/` contains run traces + summaries. The history
  generator indexes **98 operating runs** and **40 builds** into
  `notes/{run,build,session}_history.md` (generated, regenerable).
- **Tests:** CI `test-gate.yml` runs both engines + verify scripts on push/PR.
- **Guards:** `ResourceGuard` (item + byte budgets) and `CycleLock` (concurrency)
  enforced at the cycle gate for both engines.
- **Scheduler:** `operating-cycle.yml` runs the cycle on schedule and uploads
  trace + history artifacts.

## 2. What was personally inspected
- Not applicable to this layer yet: this build is AI-executed; the seat's own
  inspection points are the printed `pending_review` queue, the generated
  `notes/*` artifacts, and the CI logs. Those are the artifacts to open.

## 3. Decisions made (AI-proposed, human owns)
- LangGraph as default executor with env-var rollback (**ADR-004**) — rollback is
  a config flip, no code revert.
- Observability as committed, generated artifacts; no public runtime dashboard
  (**ADR-005**).
- Resource + concurrency guards as the outermost box (**guard.py**).
- Employees as thin adapters over existing agents (**ADR-002**) so both engines
  share the same substrate.
- Policy Engine as sole authority, fail-closed (**ADR-003**).

## 4. What AI did
- Generated this operating layer: the employee adapters, the LangGraph graph +
  ROLE_ORDER, the engine switch, guard, checkpoint helpers, history generator,
  CI workflows, and this documentation set. That is the AI contribution; it is
  marked as such here and in the commit history.

## 5. What was accepted without independent verification
- The **98-run / 40-build** history figures were produced by running the
  generator; they are counts of files on disk, not claims of machine "thinking".
  They have not been eyeballed per-file.
- No record-level data was re-verified in this layer — this is orchestration
  infrastructure, not the dataset. Dataset verification belongs to the product
  axis (`ReleaseNotes.md`, gold-set evals).

## 6. Corrections and disagreements
- A generator bug surfaced in development (list.append arity + session-day key
  normalization) and was fixed and re-run before commit. The generated artifacts
  now reconcile with `logs/operating/`.
- The operation doc set was written, then repaired where commands/links were not
  copy-true (verified against the actual module names before committing).

## 7. What remains uncertain
- Whether the scheduled cycle runs end-to-end in CI on the hosted runner with the
  pinned deps (the workflow exists; a scheduled run's success is the proof).
- Whether the review-gate pause should become the default for real (non-simulated)
  discovery windows (currently opt-in; **ADR-004** keeps it OFF).
- Whether a public runtime monitoring endpoint will be authorized later
  (**ADR-005** currently forbids it).

## 8. Time and attention
- This layer was built across the cycles recorded in `notes/session_history.md`
  and `notes/build_history.md`. Per the reporting standard: **elapsed window and
  machine runtime are visible in the build/run histories; active human attention
  is zero here by definition** (the seat has not yet opened these artifacts).
  Where human inspection happens, it must be recorded separately and will
  supersede this sentence.

---

## Addendum — 2026-08-10 (Stage 2 session)

Appended, not rewritten: the report above stands as the record of what was true when it
was written. Two of its open questions in section 7 now have answers, and section 5's
"accepted without independent verification" list grew.

**Section 7 question 1 — "Whether the scheduled cycle runs end-to-end in CI on the hosted
runner": answered, and the answer was partly NO.** Scheduled runs did execute unattended
across >48h (2026-08-08T09:09:33Z → 2026-08-10T11:00:05Z), but the commit step was
silently broken on every run by two bugs found this session: an unmatched
`data/freshness/*` glob aborting `git add` atomically, and `notes/*.md` (regenerated each
cycle by `generate_history.py`) never being staged, leaving the tree dirty so
`git pull --rebase` failed and the push was rejected. Fixed in `c9b42db` and `8e5c5a1`.
A green "Wake the operating cycle" step had been masking a red commit step.

**A stated capability turned out not to exist.** `FreshnessAgent.execute()` returned
`stale: []` hardcoded — the cross-run staleness/trust capability the contract described
had no implementation behind it, while reporting success. Implemented this session
(`src/fointel/operate/freshness_trust.py`, `2bfdc0a`) and exercised across two genuinely
separate runs (`31397630141` baseline → `31398554032` comparison). Those two runs found
no real diff, which is the honest result for a ~10-minute window in which nothing changed —
not evidence that the check works on real decay. See `docs/Stage2Status.md`.

**Two UI panels were fabricated.** "AI Employee Status" rendered hardcoded agent states
(`{name: "Discovery Pipeline", state: "active"}`) and "AI Operating Cycle" was a
decorative animation on a timer — neither read any system state, and both would have
shown "active" on a dead system. Deleted in `07cd91c` and replaced with panels counted
live from the served records.

**Section 8 (time and attention) still applies unchanged, and matters more now.** This
session's work was again AI-executed. The human seat supplied the LLM API key, the real
deadline, and the instruction to proceed; the seat has **not** performed a line-by-line
review of the files changed this session. The certification below therefore still holds
and has not been re-signed.

---

### Certification
> Every first-person statement in this report describes something the person
> signing it did or inspected. In this build the execution was performed by the
> AI assistant; the human seat has not yet personally inspected the artifacts.
> Until the seat opens `notes/*`, the CI logs, and the review queue, this report
> remains the AI's record of the machine's work, and must be treated as such —
> not as the human's account. The AI may assist; the AI may not impersonate the
> human. The report will be re-signed by the human after inspection.

Related: [Operations](Operations.md) · [Monitoring](Monitoring.md) ·
[Runbook](Runbook.md) · [Recovery](Recovery.md) ·
[RunbookMaintenance](RunbookMaintenance.md) · [RiskRegister](RiskRegister.md) ·
[SoftwareArchitecture](SoftwareArchitecture.md) ·
[CommercialArchitecture](CommercialArchitecture.md).