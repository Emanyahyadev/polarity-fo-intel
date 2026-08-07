# AI Employee Catalog — the autonomous operating system

_Generated from `agents/contract.json` (the single source of truth) by
`scripts/generate_ai_employee_catalog.py`. Do not hand-edit — run the generator._

The platform is an autonomous operating cycle driven by **14 AI Employees**
(see `src/fointel/operate/graph.py::ROLE_ORDER`). Each employee is a thin,
framework-independent adapter over an existing business agent/service. The cycle
runs identically through the LangGraph executor (default) and the legacy
deterministic Orchestrator (`FOINTEL_ENGINE`). This catalog is the executive
reference for architects, technical leads, and engineers joining the project.

## How to read this catalog

Every employee spec is the same shape: **business objective · why it exists ·
trigger · inputs · outputs · responsibilities · tools · knowledge sources ·
authority boundary · escalation conditions · upstream/downstream dependencies ·
logs/metrics · repository location · test coverage**. Everything is grounded in
the implementation — capabilities here exist in `src/`, nothing is invented.

## The cycle

```
0: scheduler
1: engineering
2: discovery
3: entity
4: duplicate
5: enrichment
6: validation
7: classification
8: governance
9: release
10: embedding
11: freshness
12: monitoring
13: logging```
scheduler -> engineering -> discovery -> entity -> duplicate -> enrichment
  -> validation -> classification -> governance -> release -> embedding
  -> freshness -> monitoring -> logging
```

## Employees

### scheduler

**Business objective.** Open and close the autonomous operating window on a schedule and register the next firing; the heartbeat of the platform.

**Why it exists.** Mission: scheduler — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 0 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - operation ('wake'|'schedule'|'retry_transient'|'skip_overlap'|'sleep'|'tick')
- jobs
- task_ids (retry/skip)
- cycle_state

**Outputs.** - opened (wake)
- closed / slept (sleep)
- scheduled (next cron)
- retried task ids
- skipped task ids

**Responsibilities.** - Wake the operating window
- Schedule the next firing
- Retry transient work
- Skip overlapping runs
- Sleep / close the window

**Tools.** - SchedulerAgent.execute (orchestrator.py)
- CycleLock (guard.py:acquire/release)

**Knowledge sources.** - repeatable schedule definition (cron / Actions schedule)

**Authority boundary.** May open/close the window, register a schedule, and rechedule/skip overlapping work. May NEVER publish data or modify the policy authority matrix.

**Autonomous actions.** wake, tick, schedule, retry_transient, sleep, skip_overlap

**Escalation conditions.** - multiple consecutive critical failures -> pause the cycle and escalate to a human (tier 2/3)

**Upstream dependencies.** (none)  ·  **Downstream dependencies.** engineering

**Consumes / Produces.** consumes: execution lock / window state · produces: open-window signal, schedule registration, run lifecycle record

**Logs produced.** - scheduler.wake
- scheduler.sleep
- log events

**Metrics produced.** _(none)_

**Checkpoint support.** False  ·  **Human approval.** n/a — scheduler is time-gating only

**Framework independence.** Yes — SchedulerEmployee (adapters.py) wraps schedulerAgent (orchestrator.py); no langgraph import.

**Repository location.** src/fointel/operate/orchestrator.py, src/fointel/operate/adapters.py, src/fointel/operate/guard.py

**Unit tests.** - test_employee_contract.py
- test_fourteen_employees.py
- test_stage2_operate.py

**Integration tests.** - test_langgraph_cycle.py
- test_engine_switch.py

---
### engineering

**Business objective.** Act as Chief Engineer — inspect system state and dispatch the cycle's work, ordering roles, and pausing stages whose precondition is unsafe or vacuous.

**Why it exists.** Mission: engineering — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 1 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - cycle_state

**Outputs.** - plan (ordered stages)
- paused_stages
- decision
- priority

**Responsibilities.** - Inspect cycle_state
- Build the ordered execution plan
- Prioritize work
- Pause unsafe stages
- Never fabricate work on an empty pool

**Tools.** - engineeringAgent.execute (cycle.py)
- PolicyEngine.decide

**Knowledge sources.** - cycle_state snapshot

**Authority boundary.** May dispatch/prioritize/pause for recovery. Never bypass policy, never override a governance decision.

**Autonomous actions.** dispatch, prioritize, route, pause_for_recovery

**Escalation conditions.** - subsystem reports critical failure, or evidence is missing for a required decision

**Upstream dependencies.** scheduler  ·  **Downstream dependencies.** discovery

**Consumes / Produces.** consumes: cycle_state · produces: plan, pause decision, priority signal

**Logs produced.** - engineering.dispatch (plan + paused_stages)

**Metrics produced.** - paused_stage count

**Checkpoint support.** stateless per cycle  ·  **Human approval.** n/a

**Framework independence.** Yes — EngineeringEmployee wraps cycle.EngineeringAgent; no langgraph import.

**Repository location.** src/fointel/operate/cycle.py, src/fointel/operate/adapters.py, policies/authority.json

**Unit tests.** - test_employee_contract.py
- test_fourteen_employees.py
- test_stage2_operate.py

**Integration tests.** - test_langgraph_cycle.py
- test_engine_switch.py

---
### discovery

**Business objective.** Discover candidate family offices from configured external lenses and persist them to the candidate POOL ONLY — never to the production dataset.

**Why it exists.** Mission: discovery — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 2 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - sources
- per_source_limit
- cycle_state

**Outputs.** - yielded (count)
- persisted (unique_added)
- resolved_firms
- pool_size
- per_source yield
- query/source

**Responsibilities.** - Harvest external sources
- Persist unique candidates to the pool
- Report per-source yield
- Retry transient harvest
- Log zero-yield as normal

**Tools.** - discovery.harvest.harvest
- get_repository (store)
- discovery.retry

**Knowledge sources.** - SEC EDGAR full-text
- IRS 990-PF (ProPublica)
- curated Wikipedia/Wikidata colliders
- GDELT (signals-primary)

**Authority boundary.** May search, collect candidates and retry. Never publishes to the dataset; never guesses classification.

**Autonomous actions.** search, collect_candidate, retry

**Escalation conditions.** - a source repeatedly errors or returns zero candidates -> escalate (but degrade to a logged gap, never sink the cycle)

**Upstream dependencies.** engineering  ·  **Downstream dependencies.** entity

**Consumes / Produces.** consumes: external source config, repository write handle · produces: candidate records in the candidate pool channel

**Logs produced.** - discovery.search (yield/per-source)
- skip/error events

**Metrics produced.** - yielded
- persisted
- resolved_firms
- pool_size

**Checkpoint support.** false  ·  **Human approval.** n/a

**Framework independence.** Yes — DiscoveryEmployee re-injects sources/limit into the agent; no langgraph import.

**Repository location.** src/fointel/discovery/harvest.py, src/fointel/operate/adapters.py, src/fointel/operate/orchestrator.py, policies/authority.json

**Unit tests.** - test_discovery.py
- test_employee_contract.py
- test_stage2_operate.py

**Integration tests.** - test_langgraph_cycle.py
- test_engine_switch.py

---
### entity

**Business objective.** Normalise org names and resolve candidate aliases/identifiers with affirmative evidence, merging only high-confidence duplicates and emitting every merge decision.

**Why it exists.** Mission: entity — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 3 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - candidates

**Outputs.** - resolved
- merges (count + decisions)
- possible_duplicates
- decisions

**Responsibilities.** - Normalize names
- Resolve aliases/identifiers
- Merge high-confidence duplicates
- Flag ambiguous duplicates
- Emit every merge decision

**Tools.** - EntityResolver

**Knowledge sources.** - candidate identifier (CRD/CIK)
- name+geography evidence

**Authority boundary.** May normalize, resolve, and merge only on affirmative evidence. Never merges on a guess.

**Autonomous actions.** normalize, resolve, merge_high_confidence_duplicate

**Escalation conditions.** - ambiguous duplicate -> stay distinct and escalate (never guess)

**Upstream dependencies.** discovery  ·  **Downstream dependencies.** duplicate

**Consumes / Produces.** consumes: candidate pool, name+geo/identifier evidence · produces: resolved identity list, merge/keep-distinct decisions

**Logs produced.** - entity.resolve with merge decisions

**Metrics produced.** - resolved
- merges
- possible_duplicates

**Checkpoint support.** False  ·  **Human approval.** ambiguous duplicates flag for human review

**Framework independence.** Yes — EntityResolutionEmployee wraps cycle.EntityResolutionAgent.

**Repository location.** src/fointel/entity_resolution.py, src/fointel/operate/cycle.py, src/fointel/operate/adapters.py

**Unit tests.** - test_entity_resolution.py
- test_employee_contract.py

**Integration tests.** - test_langgraph_cycle.py
- test_fourteen_employees.py

---
### duplicate

**Business objective.** Post-resolution / pre-release deduplication over the enriched pool using shared-domain and name+geo evidence; every merge decision is always emitted, ambiguous duplicates never merge.

**Why it exists.** Mission: duplicate — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 4 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - records (resolved/enriched)
- resolved

**Outputs.** - kept
- merges
- possible_duplicates
- decisions (merge actions + basis)

**Responsibilities.** - Detect duplicate records
- Merge with affirmative evidence
- Flag ambiguous duplicates for review
- Emit every merge decision

**Tools.** - assemble.dedupe_records

**Knowledge sources.** - shared domain
- name+geo evidence

**Authority boundary.** May only merge on shared domain or name+geo evidence. NEVER merges an ambiguous duplicate.

**Autonomous actions.** detect, flag_ambiguous

**Escalation conditions.** - ambiguous duplicates stay distinct and flag for review (never merge)

**Upstream dependencies.** entity  ·  **Downstream dependencies.** enrichment

**Consumes / Produces.** consumes: resolved records, name+geo/domain evidence · produces: deduplicated record list, merge decision journal

**Logs produced.** - duplicate.detect with merge/keep basis

**Metrics produced.** - kept
- merges
- possible_duplicates

**Checkpoint support.** False  ·  **Human approval.** ambiguous duplicates flagged to governance for human review

**Framework independence.** Yes — DuplicateDetectionEmployee wraps cycle.DuplicateDetectionAgent.

**Repository location.** src/fointel/assemble.py, src/fointel/operate/cycle.py, src/fointel/operate/adapters.py

**Unit tests.** - test_dedupe.py
- test_employee_contract.py

**Integration tests.** - test_langgraph_cycle.py
- test_fourteen_employees.py

---
### enrichment

**Business objective.** Fetch authoritative facts (SEC, IAPD/ADV, 13F, firm website) and fill candidate fields WITH provenance; an unconfirmable blank stays honestly blank (could_not_verify).

**Why it exists.** Mission: enrichment — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 5 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - candidates

**Outputs.** - enriched (count)
- filled (count)
- report (per-candidate enrichable fields)

**Responsibilities.** - Fetch authoritative facts
- Fill fields with provenance
- Collect evidence
- Keep unconfirmable fields honestly blank

**Tools.** - SEC EDGAR parser
- IAPD/ADV enricher
- 13F enricher
- website enricher
- assemble.enrich_and_build / _FILLABLE

**Knowledge sources.** - SEC EDGAR
- IAPD/ADV
- SEC 13F
- firm website

**Authority boundary.** May enrich and fill only with sourced values carrying provenance. Never guesses a blank.

**Autonomous actions.** fetch, fill_field, collect_evidence

**Escalation conditions.** - an unconfirmable field stays honestly blank (could_not_verify)

**Upstream dependencies.** duplicate  ·  **Downstream dependencies.** validation

**Consumes / Produces.** consumes: candidate raw evidence · produces: enriched record fields with provenance, enrichment report

**Logs produced.** - enrichment.fetch with enrichable-field report

**Metrics produced.** - enriched
- filled

**Checkpoint support.** False  ·  **Human approval.** n/a

**Framework independence.** Yes — EnrichmentAgent reuses existing enrichers after duplicate.

**Repository location.** src/fointel/assemble.py, src/fointel/enrichment/, src/fointel/operate/cycle.py, src/fointel/operate/adapters.py

**Unit tests.** - test_enrichment_sec.py
- test_enrichment_website.py

**Integration tests.** - test_fourteen_employees.py
- test_langgraph_cycle.py

---
### validation

**Business objective.** Apply the platform's release gates to each candidate and produce a structured per-record pass/fail verdict; never auto-pass missing evidence.

**Why it exists.** Mission: validation — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 6 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - candidates
- cycle_state

**Outputs.** - validated (per-gate result list)
- passed (count)
- failures (per-gate failure detail)

**Responsibilities.** - Evaluate the release gates per candidate
- Check required fields/evidence
- Collect evidence
- Report per-record pass/fail

**Tools.** - ReleaseGate.evaluate
- schema.FamilyOfficeRecord

**Knowledge sources.** - authoritative evidence per record
- config/inclusion_standard.md (the human standard)

**Authority boundary.** May <pass | fail> records against the release gates. Never auto-pass missing evidence.

**Autonomous actions.** review, check, collect_evidence

**Escalation conditions.** - conflicting sources / insufficient evidence -> escalate

**Upstream dependencies.** enrichment  ·  **Downstream dependencies.** classification

**Consumes / Produces.** consumes: resolved/enriched candidates · produces: per-record validation verdicts

**Logs produced.** - validation.review verdicts (passed/failed detail)

**Metrics produced.** - passed
- failures

**Checkpoint support.** False  ·  **Human approval.** gate failures escalate to governance/human

**Framework independence.** Yes — ValidationEmployee/ValidationAgent reuse ReleaseGate; no langgraph.

**Repository location.** src/fointel/validation/gates.py, src/fointel/schema.py, src/fointel/operate/cycle.py

**Unit tests.** - test_gates.py
- test_employee_contract.py

**Integration tests.** - test_langgraph_cycle.py
- test_fourteen_employees.py

---
### classification

**Business objective.** Classify each entity as SFO / MFO / Undetermined using affirmative evidence only — never guess; anything uncertain escalates for human review.

**Why it exists.** Mission: classification — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 7 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - records (resolved/validated)

**Outputs.** - classified (name, fo_type, confidence, evident)
- escalated_uncertain (names)
- assigned (count)

**Responsibilities.** - Classify SFO
- Classify MFO
- Keep Undetermined when evidence is missing
- Escalate uncertain/undetermined

**Tools.** - firm_type.classify

**Knowledge sources.** - firm website self-identification
- SEC Form ADV Item 5.F
- registration status (Family Office Rule)

**Authority boundary.** May assign a concrete type ONLY when classify() qualifies. Never guesses below confidence.

**Autonomous actions.** classify_sfo, classify_mfo

**Escalation conditions.** - evidence insufficient or confidence in the gray zone (0.70-0.85) -> stay Undetermined and escalate

**Upstream dependencies.** validation  ·  **Downstream dependencies.** governance

**Consumes / Produces.** consumes: resolved/validated records · produces: spectrum SFO/MFO/Undetermined labels with evidence flag

**Logs produced.** - classification.classify records + escalated_uncertain

**Metrics produced.** - assigned
- escalated_uncertain count

**Checkpoint support.** False  ·  **Human approval.** undetermined / gray-zone confidence -> escalate to governance, then human

**Framework independence.** Yes — ClassificationAgent reuses firm_type.classify.

**Repository location.** src/fointel/validation/firm_type.py, src/fointel/operate/cycle.py

**Unit tests.** - test_firm_type.py
- test_employee_contract.py

**Integration tests.** - test_langgraph_cycle.py
- test_policy_gates_graph.py

---
### governance

**Business objective.** Apply the Policy Engine's confidence bands and minimum-source rule to every classified candidate: approve / quarantine / escalate. The single authority on what leaves the pool.

**Why it exists.** Mission: governance — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 8 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - records (classified)

**Outputs.** - decisions (approve/escalate + reason)
- approved (+confidence)
- to_release (count)

**Responsibilities.** - Apply policy to each record
- Approve records above threshold
- Quarantine below-threshold
- Escalate gray-zone / conflicts
- Populate the human review queue

**Tools.** - PolicyEngine.decide
- PolicyEngine.may_publish
- PolicyEngine.confidence_authority

**Knowledge sources.** - policies/authority.json
- policies/contacts.json

**Authority boundary.** Approves only above minimum confidence+sources; never bypasses the policy engine.

**Autonomous actions.** approve, quarantine, apply_policy

**Escalation conditions.** - policy conflict, unusual data, release exception, confidence gray zone (0.70-0.85)

**Upstream dependencies.** classification, freshness flags  ·  **Downstream dependencies.** release, human_approval

**Consumes / Produces.** consumes: classified records, policy authority matrix · produces: governance decisions, approve/quarantine/escalate routing, human-review queue items

**Logs produced.** - governance.release_decision decisions

**Metrics produced.** - decisions
- approved
- to_release

**Checkpoint support.** False  ·  **Human approval.** require_human_review => the graph parks at the human_approval node between governance and release

**Framework independence.** Yes — GovernanceAgent reuses PolicyEngine; the interrupt node is in checkpoint.py (graph concern).

**Repository location.** src/fointel/operate/policy_engine.py, src/fointel/operate/graph.py, src/fointel/operate/checkpoint.py, policies/authority.json

**Unit tests.** - test_policy_gates_graph.py
- test_employee_contract.py

**Integration tests.** - test_checkpoint_interrupt.py
- test_langgraph_cycle.py
- test_fourteen_employees.py

---
### release

**Business objective.** Public ONLY governance-approved records into the production dataset (data/final) and version the release. A record that governance did not approve never ships.

**Why it exists.** Mission: release — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 9 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - decisions (approved)
- out_dir (default data/final)

**Outputs.** - published (names)
- count
- note

**Responsibilities.** - Publish approved records
- Version the release
- Refresh the indexed document
- Refuse unauthorized publishes

**Tools.** - export_dataset
- get_repository (store)

**Knowledge sources.** - governance-approved decisions

**Authority boundary.** May publish ONLY approved records and version the release. Never. publishes unapproved / overwrites human-verified / deletes production records.

**Autonomous actions.** publish, version_release, refresh_index_doc

**Escalation conditions.** - release gate not fully passed -> does not ship

**Upstream dependencies.** governance, human_approval  ·  **Downstream dependencies.** embedding

**Consumes / Produces.** consumes: approved list from governance · produces: production family-office dataset / versioned release

**Logs produced.** - release.publish (published, count, note)

**Metrics produced.** - published count

**Checkpoint support.** False  ·  **Human approval.** release.publish is gated: only what governance + (opt-in) human approval says may ship

**Framework independence.** Yes — ReleaseAgent wraps export_dataset.

**Repository location.** src/fointel/export.py, src/fointel/operate/cycle.py, data/final

**Unit tests.** - test_export.py

**Integration tests.** - test_langgraph_cycle.py
- test_engine_switch.py

---
### embedding

**Business objective.** Refresh the RAG vector corpus after a governed release so the live service answers from today's dataset, re-embedding idempotently and only when the release changed what is served.

**Why it exists.** Mission: embedding — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 10 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - out_dir (data/final)
- cycle_state

**Outputs.** - updated (bool)
- records (indexed count)
- metrics.embedding

**Responsibilities.** - Detect the release changed the served dataset
- Re-embed the release-authorized corpus
- Whether it idempotently skip a repeat index refresh

**Tools.** - rag.index.precompute_and_save
- rag.load.load_records_from_csv
- sentence-transformers embedder

**Knowledge sources.** - released family_offices.csv
- RAG doc corpus

**Authority boundary.** May only refresh the index over release-authorized records; never embeds unapproved records.

**Autonomous actions.** update

**Escalation conditions.** - never; skip is the safe default if nothing changed

**Upstream dependencies.** release  ·  **Downstream dependencies.** freshness

**Consumes / Produces.** consumes: released dataset CSV · produces: vector corpus + embedding focus docs

**Logs produced.** - embedding.update (updated, records)

**Metrics produced.** - metrics.embedding (updated, records, docs, focus)

**Checkpoint support.** False  ·  **Human approval.** n/a

**Framework independence.** Yes — EmbeddingUpdateAgent reuses rag.index directly; no langgraph in adapters.

**Repository location.** src/fointel/rag/index.py, src/fointel/rag/load.py, src/fointel/operate/cycle.py

**Unit tests.** - test_employee_contract.py
- test_fourteen_employees.py

**Integration tests.** - test_langgraph_cycle.py

---
### freshness

**Business objective.** Measure how current every release-authorized record is by comparing data_as_of to today; flag stale / inactive records for governance refresh.

**Why it exists.** Mission: freshness — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 11 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - records (approved)

**Outputs.** - snapshot (metrics.freshness)
- stale (flagged)

**Responsibilities.** - Detect stale records
- Refresh stale records
- Mark inactive records
- Record a freshness snapshot

**Tools.** - ComputeEngine.freshness_snapshot

**Knowledge sources.** - record data_as_of fields
- current date (today)

**Authority boundary.** Detects and flags staleness and refresh; it must never silently drop a record.

**Autonomous actions.** detect_stale, refresh, mark_inactive

**Escalation conditions.** - stale/inactive flags escalate to governance; never silently dropped

**Upstream dependencies.** embedding  ·  **Downstream dependencies.** monitoring

**Consumes / Produces.** consumes: approved records with data_as_of · produces: freshness snapshot, stale/inactive flags for governance

**Logs produced.** - freshness.detect_stale snapshot

**Metrics produced.** - snapshot (metrics.freshness)
- stale count

**Checkpoint support.** False  ·  **Human approval.** stale/inactive flags go to governance

**Framework independence.** Yes — FreshnessAgent reuses ComputeEngine.freshness_snapshot.

**Repository location.** src/fointel/compute.py, src/fointel/operate/cycle.py

**Unit tests.** - test_employee_contract.py
- test_fourteen_employees.py

**Integration tests.** - test_langgraph_cycle.py

---
### monitoring

**Business objective.** Emit a run-health and coverage snapshot (counts of each threaded list, trace size predictions, errors, escalations). A passive observer, never decides.

**Why it exists.** Mission: monitoring — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 12 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - cycle_state

**Outputs.** - snapshot (candidates/resolved/records/approved/quarantined/escalated/errors)

**Responsibilities.** - Compute a coverage snapshot
- Emit the monitoring_snapshot event
- Flag any error/escalation counts

**Tools.** - cycle_state read
- orchestrator cycle trace emit

**Knowledge sources.** - threaded cycle state

**Authority boundary.** Observes and reports. Never decides; never mutates content.

**Autonomous actions.** check_health

**Escalation conditions.** - n/a — passive observer

**Upstream dependencies.** freshness  ·  **Downstream dependencies.** logging

**Consumes / Produces.** consumes: cycle_state channels · produces: monitoring_snapshot event, health metrics block

**Logs produced.** - task_done monitoring.check_health with snapshot

**Metrics produced.** - snapshot counts (candidates, resolved, records, approved, quarantined, escalated, errors)

**Checkpoint support.** False  ·  **Human approval.** n/a

**Framework independence.** Yes — MonitoringAgent is self-contained and also feeds the snapshot under the LangGraph adapter.

**Repository location.** src/fointel/operate/cycle.py, src/fointel/operate/adapters.py

**Unit tests.** - test_employee_contract.py
- test_fourteen_employees.py

**Integration tests.** - test_langgraph_cycle.py
- test_stage2_operate.py

---
### logging

**Business objective.** Write the structured cycle log, metrics and audit trail for every step of every run; a passive, always-present recorder.

**Why it exists.** Mission: logging — see the in-code EmployeeContract in `src/fointel/operate/adapters.py`.

**Trigger.** Position 13 of 14 in the cycle (`ROLE_ORDER`); the cycle runs on schedule via `.github/workflows/operating-cycle.yml`.

**Inputs.** - cycle_state
- kind
- content

**Outputs.** - logged (kind)
- run report

**Responsibilities.** - Emit structured events
- Produce the run report
- Record metrics and audit trail
- Never hide errors

**Tools.** - orchestrator.trace.emit
- logging

**Knowledge sources.** - cycle events

**Authority boundary.** Records only; never hides errors or mutates decisions.

**Autonomous actions.** write, report, metric

**Escalation conditions.** - never — always a passive observer

**Upstream dependencies.** monitoring  ·  **Downstream dependencies.** (none)

**Consumes / Produces.** consumes: cycle_state · produces: JSONL audit trail, run report, metrics block

**Logs produced.** - logging.write (kind/ content)
- cycle_report

**Metrics produced.** - run report metrics

**Checkpoint support.** False  ·  **Human approval.** n/a

**Framework independence.** Yes — LoggingEmployee wraps LoggingAgent; emits through the trace.

**Repository location.** src/fointel/operate/orchestrator.py, src/fointel/operate/adapters.py

**Unit tests.** - test_employee_contract.py

**Integration tests.** - test_langgraph_cycle.py
- test_engine_switch.py

---
