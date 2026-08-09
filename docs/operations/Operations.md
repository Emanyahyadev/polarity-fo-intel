# Operations — Autonomous Operating Cycle

Architecture decision record: **ADR-001**, **ADR-002**, **ADR-003**.

This system runs a **scheduled, autonomous operating cycle** that keeps the
Polarity FO Intel product current. It is an operating *system*, not a demo:
one self-contained read-evaluate-write loop that is launched by cron / CI and
inflicts no state except what it can prove.

This document is the single operating model for that system. Every later doc
(Runbook, Recovery, RiskRegister, Monitoring, RunbookMaintenance) hangs off it.

---

## 1. Mental model

The product data is not static. To stay trustworthy it must be periodically:

1. **Discovered** — new candidate family offices enter a pool.
2. **Resolved & deduplicated** — candidates are tied to a canonical entity.
3. **Enriched** — gaps are filled from additional lenses.
4. **Validated — firm facts are corroborated.**
5. **Classified** — each record gets an honest SFO/MFO/Undetermined label.
6. **Governed** — the Policy Engine decides what may leave the pool.
7. **Released** — approved records are promoted into the production dataset.
8. **Re-embedded, freshened, monitored, logged** — the cycle closes.

The operating system executes that loop on a schedule, decides nothing outside
its authority matrix, writes an auditable trace for every run, and queues any
judgment call for a human seat — never guessing.

## 2. The cycle (the 14-engineer cognitive loop)

One operating run walks **14 employees** in a fixed order
(`ROLE_ORDER`, graph.py:62):

```
scheduler -> engineering -> discovery -> entity -> duplicate -> enrichment
  -> validation -> classification -> governance -> release -> embedding
  -> freshness -> monitoring -> logging
```

Every employee is a thin adapter (`adapters.py`) that **delegates** to already
existing business agents — nothing re-implements logic.

| Step | Responsibility |
|------|----------------|
| scheduler | Wake; contend for the cycle lock (skip on overlap). |
| engineering | Inspect state, build the ordered plan, pause unsafe/vacuous stages. |
| discovery | Harvest candidate FO candidates into the **pool** only. |
| entity | Resolve the canonical identity of each candidate. |
| duplicate | Collapse records that resolve to the same entity. |
| enrichment | Add cross-lens detail (entity-level intelligence). |
| validation | Corroborate firm facts to the verification standard. |
| classification | Label each firm SFO / MFO / Undetermined honestly. |
| governance | Apply the Policy Engine; decide what may be promoted. |
| release | Promote approved records into the production dataset. |
| embedding | Refresh/update vector embeddings for retrieval. |
| freshness | Re-check already-released records against external lenses. |
| monitoring | Raise on drift, anomalies, budget overruns. |
| logging | Close the trace and run summary. |

## 3. The Policy Engine — authority in code

Eman's engineering judgment is encoded in **`policies/authority.json`** and
**`policies/contacts.json`** and enforced by `policy_engine.py` **before** any
action runs (enforcement in control flow, not prose).

Every proposed action is resolved to one of three tiers:

- **Tier 1 — autonomous:** the action is on the allow-list and the engine
  proceeds.
- **Tier 2 — escalate:** the action needs Eman's seat; it is queued to the
  `HumanReviewQueue`, the employee is **not** run.
- **Tier 3 — refuse:** a hard `never` rule; permanently off.

`graph.py` routes to **END** on any refuse/escalate — control never continues
past an action the engine did not approve. `decide()` also returns
`AuthorityDecision` for confidence-based release (`may_publish`) and the contact
standard (`contact_review`, which refuses generic mailboxes as named-person
routes).

## 4. Execution engines — one switch, dual path

`FOINTEL_ENGINE` selects the executor; default is `langgraph`:

- `langgraph` — a LangGraph `StateGraph` over the same employees. Checkpointed.
- `orchestrator` — the legacy deterministic loop (rollback path).

**Both engines run identical employees, the same Policy Engine, thread the same
cycle state, write the same JSONL trace, fill the same review queue.** The
only difference is the executor (see `engine.py`, Phase 5). The env var is the
rollback: flip it, no code change. ADR-004 records the migration bet.

```
python operations/operate.py --simulate              # LangGraph (default)
FOINTEL_ENGINE=orchestrator python operations/operate.py --simulate
```

## 5. Guards (outermost box)

- **ResourceGuard** — caps list-channel item counts and total serialized cycle
  state size. Applied at the cycle gate (before work) so a runaway pool or an
  oversized threaded state is refused, never silently truncated.
- **CycleLock** — a process-wide mutex so two scheduler fires cannot write the
  same trace/repository concurrently (scheduler overlap guard).

The guards are orchestration concerns that do **not** duplicate policy
decisions; the Policy Engine remains the sole authority on *business* actions.

## 6. Checkpointing & review gate

- Checkpointing is orchestration, routed through the same `Repository`
  abstraction as data — SQLite in dev, Postgres/Supabase when `DATABASE_URL` is
  set. A cycle paused on one layer resumes on the other with no decision
  difference.
- A review node sits **between governance and release**. It is opt-in
  (`cycle["require_human_review"]=True`): it parks via a LangGraph `interrupt`
  listing pending queue items; resume with
  `{"decision": "approved"}` continues. **Default OFF** keeps the autonomous
  path identical.

## 7. Entry points

- `operations/operate.py --simulate` — the operator entry point (one cycle).
- GitHub Actions `operating-cycle.yml` — scheduled cron driver.
- GitHub Actions `test-gate.yml` — push/PR gate running both engines in tests.

## 8. Artifacts the system produces

- `logs/operating/*.jsonl` — raw per-run trace (task_done events + decisions).
- `logs/operating/*-summary.json` — canonical per-run summary.
- `notes/{run,build,session}_history.md` — durable history index, **generated**
  by `scripts/generate_history.py` from the traces + git (never hand-edited).
- `HumanReviewQueue` — the review queue where judgment is applied.

## 9. Key files

```
operations/operate.py            the one entry point
src/fointel/operate/engine.py    engine routing switch
src/fointel/operate/graph.py    LangGraph StateGraph + ROLE_ORDER
src/fointel/operate/adapters.py  14 employee adapters
src/fointel/operate/policy_engine.py  authority in code
src/fointel/operate/guard.py     resource + concurrency guards
src/fointel/operate/checkpoint.py checkpointing + review gate
scripts/generate_history.py      history artifact generator
.github/workflows/*.yml          cron + test gate + operating cycle
```

Related: [Runbook](Runbook.md) · [Recovery](Recovery.md) ·
[Monitoring](Monitoring.md) · [RiskRegister](RiskRegister.md) ·
[RunbookMaintenance](RunbookMaintenance.md) ·
[Architecture](Architecture.md) (product architecture).