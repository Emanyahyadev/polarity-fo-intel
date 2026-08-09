# CommercialArchitecture — how the operating system earns its place

ADRs: **ADR-001** (cycle), **ADR-005** (observability), **ADR-006** (recovery).
Related: [SoftwareArchitecture](SoftwareArchitecture.md) (the operating-system
asset view) and the product [Architecture](../Architecture.md) /
[Task2_SaaS_Conversion](../Task2_SaaS_Conversion.md).

## 1. The pitch
"Polarity FO Intelligence" is a **live, autonomous** family-office intelligence
system: the dataset is never stale by construction, every refresh is
auditable, and anything the machine cannot prove waits for a human seat
instead of being sold. That is the commercial differentiator — honesty under
sampling, freshness on a schedule.

## 2. Who pays
- **The assessment** (data-first acceptance): the operating system keeps the
  55-record dataset honest and current, which is exactly what the acceptance
  criteria test.
- **Future buyers** (SaaS, Task2): a family-office lead-gen subscription whose
  data *regenerates* without a human babysitting connectors — the operating
  system is the product's clock.

## 3. Commercial boundaries we keep
- **No fabricated freshness.** A cycle that does nothing is *success*; we never
  report an empty window as growth. Claims in any future deck must reconcile
  with `notes/run_history.md`.
- **No public runtime dashboard** (ADR-005) — observability is committed,
  auditable artifacts, not a marketing endpoint.
- **The review seat is a feature.** The queue that keeps judgment with Eman is a
  sales point ("AI builds, human owns the standard"), not a bug to hide.

## 4. Recurring revenue mechanics (from the operating system's view)
1. Scheduled cycle refreshes discovery/enrichment/validation/classification.
2. Governance gates releases by confidence + source count (Policy Engine).
3. Human seat resolves what needs judgment; the cycle threads that decision.
4. History artifacts prove the refresh is real (per-run traces + summaries).

## 5. Risks to the commercial story
- **Silent drift** (R5 in RiskRegister) — no schedule → stale data → dishonest
  freshness claims. Mitigated by Monitoring + Recovery discipline.
- **Relabeling temptation** — selling an "SFO" the data cannot defend. Blocked
  by the honest-label rule (Rule 2, product docs) and the Policy Engine.

## 6. Where the money sits in the repo
- The dataset + verification scripts = the sellable asset (product axis).
- The operating system = the guarantee that the asset stays sellable.
- The history artifacts = the evidence both are true.

Related: [Task2_SaaS_Conversion](../Task2_SaaS_Conversion.md) ·
[SoftwareArchitecture](SoftwareArchitecture.md) ·
[Operations](Operations.md).