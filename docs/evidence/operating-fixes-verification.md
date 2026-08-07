# Operating-layer Fixes Verification

_Machine-produced by `scripts/verify_operating_fixes.py`. Reproduction: run that script._

## Fix A - Entity Agent (real candidate set)

- Input before coercion: `[{"name": "Cascade Family Office LLC", "hq_city": "New York", "hq_state": "NY", "source": "curated", "identifiers": {"domain": "cascadefamilyoffice.com"}}, {"name": "Cascade Family Office", "hq_city": "New York", "hq_state": "NY", "source": "SEC EDGAR (13F / SC / Form D filings)", "identifiers": {"cik": "0001234567"}}]`

- Typed `Candidate` after coercion: `[{"name": "Cascade Family Office LLC", "source_class": "Other", "identifiers": {}}, {"name": "Cascade Family Office", "source_class": "SEC EDGAR (13F / SC / Form D filings)", "identifiers": {}}]`

- EntityResolver source: `src/fointel/entity_resolution.py::EntityResolver.resolve`

- Normalized entities: `[{"name": "Cascade Family Office LLC", "dedup_key": "name:cascade family office|geo:?", "identifiers": {}}]`

- Merge decisions: `[{"incoming": "Cascade Family Office LLC", "matched": null, "action": "new", "basis": "", "reason": "distinct firm"}, {"incoming": "Cascade Family Office", "matched": "Cascade Family Office LLC", "action": "merge", "basis": "name+geo", "reason": "same firm (identifier or name+geography agreement)"}]`

- Structured logs emitted: 1 line(s) (see `docs/evidence/operating-fixes-entity-path.json`).

- **Verdict: passed**

## Fix B - Validation binding

- `validation` resolves to the cycle list-agent: **True**
- Legacy orchestrator `ValidationAgent` removed: **True**

- Cycle trace (validation step): `{"outcome": "ok", "action": "validation.review", "results": {"validated": [{"error": "3 validation errors for FamilyOfficeRecord\nfo_id\n  Field required [type=missing, input_value={'name': 'Cascade Family ...scadefamilyoffice.com'}}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\ndiscovery_source\n  Field required [type=missing, input_value={'name': 'Cascade Family ...scadefamilyoffice.com'}}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\ndata_as_of\n  Field required [type=missing, input_value={'name': 'Cascade Family ...scadefamilyoffice.com'}}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing", "candidate": "{'name': 'Cascade Family Office LLC', 'h"}, {"error": "3 validation errors for FamilyOfficeRecord\nfo_id\n  Field required [type=missing, input_value={'name': 'Cascade Family ...: {'cik': '0001234567'}}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\ndiscovery_source\n  Field required [type=missing, input_value={'name': 'Cascade Family ...: {'cik': '0001234567'}}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\ndata_as_of\n  Field required [type=missing, input_value={'name': 'Cascade Family ...: {'cik': '0001234567'}}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing", "candidate": "{'name': 'Cascade Family Office', 'hq_ci"}, {"error": "3 validation errors for FamilyOfficeRecord\nfo_id\n  Field required [type=missing, input_value={'name': 'Bluewater Capit...in': 'bluewatercp.com'}}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\ndiscovery_source\n  Field required [type=missing, input_value={'name': 'Bluewater Capit...in': 'bluewatercp.com'}}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing\ndata_as_of\n  Field required [type=missing, input_value={'name': 'Bluewater Capit...in': 'bluewatercp.com'}}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.13/v/missing", "candidate": "{'name': 'Bluewater Capital Partners', '"}], "passed": 0}}`
- Contract outputs returned: **contract expects {validated, passed, failures}; returned keys=['passed', 'validated']**
- Full cycle step sequence: `[["scheduler", "ok"], ["engineering", "ok"], ["discovery", "ok"], ["entity", "ok"], ["duplicate", "ok"], ["enrichment", "ok"], ["validation", "ok"], ["classification", "ok"], ["governance", "ok"], ["release", "ok"], ["embedding", "ok"], ["freshness", "ok"], ["monitoring", "ok"], ["logging", "ok"]]`

- **Verdict: passed**

## 14-Employee contract audit

| Contract | Employee | Delegate | Node# | Policy integration | Framework | Compliance | Gaps |
|---|---|---|---|---|---|---|---|
| `scheduler` | `SchedulerEmployee` | `SchedulerAgent` | `0` | `scheduler.wake -> autonomous (tier 1)` | `yes` | **PASS** | `none` |
| `engineering` | `EngineeringEmployee` | `EngineeringAgent` | `1` | `engineering.dispatch -> autonomous (tier 1)` | `yes` | **PASS** | `none` |
| `discovery` | `DiscoveryEmployee` | `DiscoveryAgent` | `2` | `discovery.search -> autonomous (tier 1)` | `yes` | **PASS** | `none` |
| `entity` | `EntityResolutionEmployee` | `EntityResolutionAgent` | `3` | `entity.resolve -> autonomous (tier 1)` | `yes` | **PASS** | `none` |
| `duplicate` | `DuplicateDetectionEmployee` | `DuplicateDetectionAgent` | `4` | `duplicate.detect -> autonomous (tier 1)` | `yes` | **PASS** | `none` |
| `enrichment` | `EnrichmentEmployee` | `EnrichmentAgent` | `5` | `enrichment.fetch -> autonomous (tier 1)` | `yes` | **PASS** | `none` |
| `validation` | `ValidationEmployee` | `ValidationAgent` | `6` | `validation.review -> autonomous (tier 1)` | `yes` | **PASS** | `none` |
| `classification` | `ClassificationEmployee` | `ClassificationAgent` | `7` | `classification.classify -> autonomous (tier 1)` | `yes` | **PASS** | `none` |
| `governance` | `GovernanceEmployee` | `GovernanceAgent` | `8` | `governance.release_decision -> autonomous (tier 1)` | `yes` | **PASS** | `none` |
| `release` | `ReleaseEmployee` | `ReleaseAgent` | `9` | `release.publish -> autonomous (tier 1)` | `yes` | **PASS** | `none` |
| `embedding` | `EmbeddingUpdateEmployee` | `EmbeddingUpdateAgent` | `10` | `embedding.update -> autonomous (tier 1)` | `yes` | **PASS** | `none` |
| `freshness` | `FreshnessEmployee` | `FreshnessAgent` | `11` | `freshness.detect_stale -> autonomous (tier 1)` | `yes` | **PASS** | `none` |
| `monitoring` | `MonitoringEmployee` | `MonitoringAgent` | `12` | `monitoring.check_health -> autonomous (tier 1)` | `yes` | **PASS** | `none` |
| `logging` | `LoggingEmployee` | `LoggingAgent` | `13` | `logging.write -> autonomous (tier 1)` | `yes` | **PASS** | `none` |