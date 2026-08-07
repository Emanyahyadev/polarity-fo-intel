# Architecture Decision Records

Accepted decisions for the **operating system** (the autonomous cycle) and the
guards/observability around it, in [ADR-001..006](.) format. Product-data
decisions live in `docs/DecisionLog.md` (D1…D28). Each ADR records the context,
the decision, and the consequences so a later engineer can reproduce the reason.

| # | Area | Decision | Link |
|---|------|----------|------|
| ADR-001 | Cycle | The operating cycle is an autonomous scheduled loop (14 employees). | [ADR-001](ADR-001.md) |
| ADR-002 | Employees | AI Employees are thin adapters over existing agents. | [ADR-002](ADR-002.md) |
| ADR-003 | Policy | The Policy Engine is the single authority, fail-closed. | [ADR-003](ADR-003.md) |
| ADR-004 | Engine | LangGraph is the default executor; env-var rollback to `orchestrator`. | [ADR-004](ADR-004.md) |
| ADR-005 | Observability | Observability as committed, generated artifacts; no public dashboards. | [ADR-005](ADR-005.md) |
| ADR-006 | Recovery | Restore-first recovery discipline with a timeline. | [ADR-006](ADR-006.md) |

Related operational docs: [Operations](Operations.md) ·
[Monitoring](Monitoring.md) · [Runbook](Runbook.md) · [Recovery](Recovery.md) ·
[RiskRegister](RiskRegister.md) · [RunbookMaintenance](RunbookMaintenance.md) ·
[SafetyGuardrails](SafetyGuardrails.md) · [OpsPRD_RND](OpsPRD_RND.md).