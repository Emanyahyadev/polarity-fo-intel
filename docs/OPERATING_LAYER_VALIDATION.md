# AI Employee Operating-Layer Validation

_Machine-produced by `scripts/generate_operating_validation_report.py` from the verification evidence in `docs/evidence/`. Reproduction: run that script; every statement below is traceable to a repository artifact or verification result._

## Scope and method

This validates the **14 AI Employees** of the autonomous operating cycle (`agents/contract.json`, `src/fointel/operate/graph.py::ROLE_ORDER`) against their implemented classes and the full test suite. Evidence sources:

- `docs/evidence/employee-contract-audit.json` — contract vs implementation matrix.
- `docs/evidence/operating-fixes-entity-path.json` — Fix A real-input entity trace.
- `docs/evidence/operating-fixb-validation.json` — Fix B binding + live cycle trace.
- Full test suite: **171 passed, 1 skipped, 1 warning in 53.13s**.

## Defects fixed during this verification

Three defects in the operating layer were found and corrected before this report was produced. Each fix is covered by a regression test.

1. **entity — crash on a populated candidate pool.** `EntityResolutionAgent` passed raw dicts to `EntityResolver.resolve`, which requires typed `Candidate` objects; `AttributeError: 'dict' object has no attribute 'raw'` on any real input. Fixed by coercing candidates to `Candidate` at the boundary (`_as_candidates`, `src/fointel/operate/cycle.py`).
2. **validation — bound to the wrong agent.** The orchestrator's single-record `ValidationAgent` was registered first and shadowed the cycle's list-processing agent, so `validation` returned `{'status':'noop'}` for a candidate list instead of `{validated, passed, failures}`. Fixed by removing the duplicate in `src/fointel/operate/orchestrator.py`.
3. **governance — crash on the classifier's `Confidence` label.** Classification emits `Confidence` (`High`/`Medium`/`Low`); governance called `float('Low')` → `could not convert string to float`. Fixed with `_confidence_score` mapping labels to the policy-engine numeric bands (`src/fointel/operate/cycle.py`).

## Full cycle execution trace (Fix B evidence)

A real non-empty candidate set driven through the compiled LangGraph cycle (discovery stubbed offline):

```
scheduler ok -> engineering ok -> discovery ok -> entity ok -> duplicate ok -> enrichment ok -> validation ok -> classification ok -> governance ok -> release ok -> embedding ok -> freshness ok -> monitoring ok -> logging ok
```

`governance` outcome after Fix C: **ok** (was `failed`). Validation step returned keys: `{validated, passed, failures}` — contract compliant (see `docs/evidence/operating-fixb-validation.json`).

## Per-employee validation

### scheduler

**1. Mission.** see `SchedulerEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/operate/orchestrator.py, src/fointel/operate/adapters.py, src/fointel/operate/guard.py.
**3. Contract compliance.** `PASS`. LangGraph node # 0 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_employee_contract.py, test_fourteen_employees.py, test_stage2_operate.py.
**5. Integration tests.** test_langgraph_cycle.py, test_engine_switch.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `scheduler`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `3 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `0 claim(s)` declared in the contract.
**9. Policy interactions.** `scheduler.wake -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

### engineering

**1. Mission.** see `EngineeringEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/operate/cycle.py, src/fointel/operate/adapters.py, policies/authority.json.
**3. Contract compliance.** `PASS`. LangGraph node # 1 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_employee_contract.py, test_fourteen_employees.py, test_stage2_operate.py.
**5. Integration tests.** test_langgraph_cycle.py, test_engine_switch.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `engineering`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `1 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `1 claim(s)` declared in the contract.
**9. Policy interactions.** `engineering.dispatch -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

### discovery

**1. Mission.** see `DiscoveryEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/discovery/harvest.py, src/fointel/operate/adapters.py, src/fointel/operate/orchestrator.py, policies/authority.json.
**3. Contract compliance.** `PASS`. LangGraph node # 2 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_discovery.py, test_employee_contract.py, test_stage2_operate.py.
**5. Integration tests.** test_langgraph_cycle.py, test_engine_switch.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `discovery`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `2 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `4 claim(s)` declared in the contract.
**9. Policy interactions.** `discovery.search -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

### entity

**1. Mission.** see `EntityResolutionEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/entity_resolution.py, src/fointel/operate/cycle.py, src/fointel/operate/adapters.py.
**3. Contract compliance.** `PASS`. LangGraph node # 3 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_entity_resolution.py, test_employee_contract.py.
**5. Integration tests.** test_langgraph_cycle.py, test_fourteen_employees.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `entity`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `1 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `3 claim(s)` declared in the contract.
**9. Policy interactions.** `entity.resolve -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

### duplicate

**1. Mission.** see `DuplicateDetectionEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/assemble.py, src/fointel/operate/cycle.py, src/fointel/operate/adapters.py.
**3. Contract compliance.** `PASS`. LangGraph node # 4 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_dedupe.py, test_employee_contract.py.
**5. Integration tests.** test_langgraph_cycle.py, test_fourteen_employees.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `duplicate`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `1 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `3 claim(s)` declared in the contract.
**9. Policy interactions.** `duplicate.detect -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

### enrichment

**1. Mission.** see `EnrichmentEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/assemble.py, src/fointel/enrichment/, src/fointel/operate/cycle.py, src/fointel/operate/adapters.py.
**3. Contract compliance.** `PASS`. LangGraph node # 5 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_enrichment_sec.py, test_enrichment_website.py.
**5. Integration tests.** test_fourteen_employees.py, test_langgraph_cycle.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `enrichment`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `1 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `2 claim(s)` declared in the contract.
**9. Policy interactions.** `enrichment.fetch -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

### validation

**1. Mission.** see `ValidationEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/validation/gates.py, src/fointel/schema.py, src/fointel/operate/cycle.py.
**3. Contract compliance.** `PASS`. LangGraph node # 6 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_gates.py, test_employee_contract.py.
**5. Integration tests.** test_langgraph_cycle.py, test_fourteen_employees.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `validation`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `1 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `2 claim(s)` declared in the contract.
**9. Policy interactions.** `validation.review -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

### classification

**1. Mission.** see `ClassificationEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/validation/firm_type.py, src/fointel/operate/cycle.py.
**3. Contract compliance.** `PASS`. LangGraph node # 7 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_firm_type.py, test_employee_contract.py.
**5. Integration tests.** test_langgraph_cycle.py, test_policy_gates_graph.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `classification`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `1 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `2 claim(s)` declared in the contract.
**9. Policy interactions.** `classification.classify -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

### governance

**1. Mission.** see `GovernanceEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/operate/policy_engine.py, src/fointel/operate/graph.py, src/fointel/operate/checkpoint.py, policies/authority.json.
**3. Contract compliance.** `PASS`. LangGraph node # 8 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_policy_gates_graph.py, test_employee_contract.py.
**5. Integration tests.** test_checkpoint_interrupt.py, test_langgraph_cycle.py, test_fourteen_employees.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `governance`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `1 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `3 claim(s)` declared in the contract.
**9. Policy interactions.** `governance.release_decision -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

### release

**1. Mission.** see `ReleaseEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/export.py, src/fointel/operate/cycle.py, data/final.
**3. Contract compliance.** `PASS`. LangGraph node # 9 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_export.py.
**5. Integration tests.** test_langgraph_cycle.py, test_engine_switch.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `release`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `1 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `1 claim(s)` declared in the contract.
**9. Policy interactions.** `release.publish -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

### embedding

**1. Mission.** see `EmbeddingUpdateEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/rag/index.py, src/fointel/rag/load.py, src/fointel/operate/cycle.py.
**3. Contract compliance.** `PASS`. LangGraph node # 10 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_employee_contract.py, test_fourteen_employees.py.
**5. Integration tests.** test_langgraph_cycle.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `embedding`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `1 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `1 claim(s)` declared in the contract.
**9. Policy interactions.** `embedding.update -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

### freshness

**1. Mission.** see `FreshnessEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/compute.py, src/fointel/operate/cycle.py.
**3. Contract compliance.** `PASS`. LangGraph node # 11 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_employee_contract.py, test_fourteen_employees.py.
**5. Integration tests.** test_langgraph_cycle.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `freshness`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `1 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `2 claim(s)` declared in the contract.
**9. Policy interactions.** `freshness.detect_stale -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

### monitoring

**1. Mission.** see `MonitoringEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/operate/cycle.py, src/fointel/operate/adapters.py.
**3. Contract compliance.** `PASS`. LangGraph node # 12 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_employee_contract.py, test_fourteen_employees.py.
**5. Integration tests.** test_langgraph_cycle.py, test_stage2_operate.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `monitoring`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `1 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `1 claim(s)` declared in the contract.
**9. Policy interactions.** `monitoring.check_health -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

### logging

**1. Mission.** see `LoggingEmployee` contract (in-app `EmployeeContract`: `mission/inputs/outputs/authority/skills`).
**2. Repository location.** src/fointel/operate/orchestrator.py, src/fointel/operate/adapters.py.
**3. Contract compliance.** `PASS`. LangGraph node # 13 of 14 (`ROLE_ORDER`).
**4. Unit tests.** test_employee_contract.py.
**5. Integration tests.** test_langgraph_cycle.py, test_engine_switch.py.
**6. Execution evidence.** present in `operating-fixb-validation.json` (cycle step `logging`) and `operating-fixes-entity-path.json` (Fix A).
**7. Logs generated.** `2 claim(s)` declared in the contract; cycle logs captured under `docs/evidence/operating-fixb-validation.json`.
**8. Metrics generated.** `1 claim(s)` declared in the contract.
**9. Policy interactions.** `logging.write -> autonomous (tier 1)` (Policy Engine consulted before the node runs; Tier 1 autonomous).
**10. Remaining issues.** none.

---

## Aggregate table

| Contract | Employee | Delegate | Node# | Compliance | Policy integration | Gaps |
|---|---|---|---|---|---|---|
| scheduler | SchedulerEmployee | SchedulerAgent | 0 | **PASS** | scheduler.wake -> autonomous (tier 1) | none |
| engineering | EngineeringEmployee | EngineeringAgent | 1 | **PASS** | engineering.dispatch -> autonomous (tier 1) | none |
| discovery | DiscoveryEmployee | DiscoveryAgent | 2 | **PASS** | discovery.search -> autonomous (tier 1) | none |
| entity | EntityResolutionEmployee | EntityResolutionAgent | 3 | **PASS** | entity.resolve -> autonomous (tier 1) | none |
| duplicate | DuplicateDetectionEmployee | DuplicateDetectionAgent | 4 | **PASS** | duplicate.detect -> autonomous (tier 1) | none |
| enrichment | EnrichmentEmployee | EnrichmentAgent | 5 | **PASS** | enrichment.fetch -> autonomous (tier 1) | none |
| validation | ValidationEmployee | ValidationAgent | 6 | **PASS** | validation.review -> autonomous (tier 1) | none |
| classification | ClassificationEmployee | ClassificationAgent | 7 | **PASS** | classification.classify -> autonomous (tier 1) | none |
| governance | GovernanceEmployee | GovernanceAgent | 8 | **PASS** | governance.release_decision -> autonomous (tier 1) | none |
| release | ReleaseEmployee | ReleaseAgent | 9 | **PASS** | release.publish -> autonomous (tier 1) | none |
| embedding | EmbeddingUpdateEmployee | EmbeddingUpdateAgent | 10 | **PASS** | embedding.update -> autonomous (tier 1) | none |
| freshness | FreshnessEmployee | FreshnessAgent | 11 | **PASS** | freshness.detect_stale -> autonomous (tier 1) | none |
| monitoring | MonitoringEmployee | MonitoringAgent | 12 | **PASS** | monitoring.check_health -> autonomous (tier 1) | none |
| logging | LoggingEmployee | LoggingAgent | 13 | **PASS** | logging.write -> autonomous (tier 1) | none |

## Evidence index

| Artifact | Backs |
|---|---|
| `employee-contract-audit.json` | 14/14 contract matrix |
| `operating-fixes-entity-path.json` | Fix A real-input entity coercion + merge |
| `operating-fixb-validation.json` | Fix B binding + live full-cycloe trace |
| `operating-fixes-verification.md` | human-readable verification summary |

The directives above are entirely derived from the repository and the recorded verification outputs. Nothing here claims a review step that has not been recorded in the review queue.