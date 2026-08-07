# System Design — the operating system

This is the **operating-system** design (the autonomous cycle that keeps the
product current). Product architecture lives in [Architecture.md](../Architecture.md)
and [Deployment.md](../Deployment.md). ADRs referenced below are in
[`docs/adr/`](../adr/).

## 1. Goal & scope
A scheduled, auditable loop that refreshes discovery → resolution → validation →
classification → governance → release → embedding, and never acts outside its
authority matrix. Scope boundary: orchestration and control only, in the box.

## 2. The two layers
1. **Product/business logic** — existing agents and services (discovery,
   entity resolution, validation, enrichment, RAG, storage). Untouched by the
   operating layer.
2. **Operating layer** — the employee frame, the Policy Engine, guards,
   checkpointing, traces, the review queue. Thin and framework-neutral.

## 3. Stages (the 14-engineer cycle)
Scheduler → Engineering → Discovery → Entity → Duplicate → Enrichment →
Validation → Classification → Governance → Release → Embedding → Freshness →
Monitoring → Logging (`graph.py::ROLE_ORDER`). Each stage is a
`_DelegatingEmployee` (ADR-002) and every one is policy-gated before it runs
(ADR-003).

## 4. The authority model — tiers
- **Tier 1 — autonomous:** on the allow-list; the employee runs.
- **Tier 2 — escalate:** queued to human review; the employee does not run.
- **Tier 3 — refuse:** hard `never`; permanently off.
On refuse/escalate the graph routes to END — control never continues past an
unapproved action.

## 5. Execution engines
`FOINTEL_ENGINE` selects `langgraph` (default) or `orchestrator` (rollback).
Both run the same employees / policy engine / state / trace / review queue
(ADR-004). The LangGraph path replays steps into the same trace contract so
consumers cannot tell the executor apart.

## 6. Guards
- **ResourceGuard:** caps list-channel item counts and serialized state bytes at
  the cycle gate.
- **CycleLock:** process-wide mutex preventing concurrent cycles on one repo.
(ADR-005 boundaries; see `guard.py`.)

## 7. Checkpointing & human approval
Checkpointing routes through the same `Repository` abstraction as data (SQLite →
Postgres/Supabase via `DATABASE_URL`). A `human_approval` node between
governance and release parks on `interrupt()` when
`cycle["require_human_review"]` is set; otherwise the autonomous path is
unchanged (ADR-004).

## 8. Interface
- CLI: `python operations/operate.py --simulate` (quiet-window cycle).
- CI: `operating-cycle.yml` (schedule) and `test-gate.yml` (change gate). No
  public runtime endpoint (ADR-005).

## 9. Non-goals / boundaries
- No production dashboard endpoint in this phase.
- No mutable, spontaneous actions — only scheduled roles run.

Related: [Operations](Operations.md) · [OpsPRD_RND](OpsPRD_RND.md) ·
[Architecture](Architecture.md).