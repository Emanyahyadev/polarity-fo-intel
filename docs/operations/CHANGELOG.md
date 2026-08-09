# CHANGELOG

Changelog for the **operating system** layer. Product data/verifies changes
live in `docs/ReleaseNotes.md` (data) and `docs/BuildLog.md` (sessions).
Version scheme follows the operating cycles that ship changes.

## [Unreleased]
- Operating documentation set added (`docs/operations/`): Operations, Monitoring,
  Runbook, Recovery, RiskRegister, RunbookMaintenance, SafetyGuardrails,
  SystemDesign, SoftwareArchitecture, CommercialArchitecture, OpsPRD_RND,
  CheckpointReport, plus the `docs/adr/ADR-001…006` decision records.
- History artifacts generated for the first time (`notes/`).

## [1.0.0] — operating layer
### Added
- Operating cycle over **14 employees** (`ROLE_ORDER`): scheduler, engineering,
  discovery, entity, duplicate, enrichment, validation, classification,
  governance, release, embedding, freshness, monitoring, logging.
- **AI Employee adapters** (`adapters.py`) — thin wrappers delegating to the
  existing agent/base business classes.
- **Engine switch** (`engine.py`) — `FOINTEL_ENGINE` selects `langgraph` (default)
  or `orchestrator` (rollback); both share the same Policy Engine / trace /
  review queue.
- **Policy Engine** (`policy_engine.py`) — fail-closed authority (Tier 1/2/3) +
  confidence-based release + contact-standard enforcement.
- **Guards** (`guard.py`) — BudgetGuard (item + serialized-size caps) and
  CycleLock (concurrency) at the outermost gate.
- **Checkpointing + review gate** (`checkpoint.py`) — Sqlite/Memory
  checkpointer + optional interrupt-based review node.
- **CI** — `test-gate.yml` (push/PR, runs both engines) and `operating-cycle.yml`
  (scheduled run + trace/history upload).

### Fixed
- Generator session-day normalization and artifact reconciliation.

## Earlier
- Product data/release phase: see `docs/ReleaseNotes.md` and
  `docs/BuildLog.md` (28-session build, 55-record dataset, Micro-RAG).