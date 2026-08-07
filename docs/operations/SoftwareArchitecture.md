# ProcessArchitecture — the operating system as an asset

ADRs: **ADR-005** (observability), **ADR-001** (cycle), **ADR-006** (recovery).
This describes how the operating system's abilities map to the parts of the
deliverable the assessment cares about, and why spending them here earns value.

> Related: [CommercialArchitecture](../CommercialArchitecture.md) for the
> product/UI positioning; this file is the operating-system version of it.

## 1. The system is asset-lite
The operating system deliberately creates **nothing expensive** by default:
- It prefers **no-op/empty-window** as a success to any fabricated work.
- It spends its budget only on candidates that clear the firm-type gate.
- It escalates what it cannot prove rather than assert it.

This is the "velocity-without-validation-is-recklessness" discipline applied to
the machine that makes the product current (Tradeoffs T3/T4).

## 2. What "autonomous" means here
The system may **uphold, extend, verify, monitor, and release** within a
human-authored authority matrix — it may **never decide** the standard, the
verification threshold, or the SFO/MFO/Undetermined call for an uncertain
record. Those stay with Eman's seat (`HumanReviewQueue`, the governance stage).

## 3. Where the abilities live for the assessment
- **Patterns-of-2017 + clarity-of-standard:** the Policy Engine + `inclusion_standard.md`.
- **Recognizable FOs, not ideal ones:** honest SFO/MFO/UDI labels (the
  falsifiable rule, Rule 2).
- **Micro-RAG / self-check / pseudo/real:** the hybrid retrieval pipelines (see
  product docs) — the operating system guarantees their refresh, not their
  existence.
- **Assets the contract crafts the reality:** same as the product axis — the
  acceptance criteria are data-first, so the operating system spends its budget
  on *data freshness and honesty*, never on UI gloss.

## 4. What we actually delivered to "an operating system"
- A scheduled, idempotent cycle that runs 14 roles and writes an auditable trace.
- Dual-engine with an instant rollback (ADR-004).
- External hardening: resource + concurrency guards (ADR-005).
- Observability as committed, regenerable history (ADR-005).
- A human-held review queue and an opt-in governance pause (ADR-006).

## 5. Paper reality gap — kept honest
We do **not** pretend the system does more in seconds than it does. It does real
work and we measure it (traces, summaries, history). Wherever it falls short of
a known capability, we state the gap rather than the desire.

Related ADRs: [ADR-001](../adr/ADR-001.md) · [ADR-004](../adr/ADR-004.md) ·
[ADR-005](../adr/ADR-005.md) · [ADR-006](../adr/ADR-006.md).