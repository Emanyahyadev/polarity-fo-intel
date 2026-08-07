# Build Session Summary

**About this document.** This summary records *what the repository shows was built*,
in the order the artifacts support, and the *recorded engineering decisions* behind
it (see `docs/DecisionLog.md`, `docs/Architecture.md`, and `docs/evidence/` for the
supporting evidence). It does **not** estimate person-hours: there is no trustworthy
basis in the repository for a total-effort figure, so no such number is stated here.
See [docs/effort-report.md](docs/effort-report.md) for the methodology and the
template the candidate fills in with her own verified figures.

## Main work phases (as evidenced in the repository)

1. **Analysis + architecture** — the brief and *How We Work* were translated into a
   layered pipeline (discovery → enrichment → validation → gate → store → RAG →
   serve) and a data model built around the two rules of proof (cell-level
   provenance; firm-level affirmative evidence). `docs/Architecture.md`,
   `docs/DecisionLog.md` (D1–D28), `docs/adr/ADR-001..006`.
2. **Discovery** — four discovery lenses against free authoritative sources; the
   Google-News-RSS ToS issue and the repositioning of news from discovery to
   signals are recorded in `docs/DecisionLog.md`. Discovery-report artifact:
   `docs/evidence/dataset-discovery-report.json`.
3. **Architecture Gate Review + remediation** — a mid-build adversarial review of
   the repo against the brief led to evidence-based entity resolution, the release
   gate as the single publication authority, provenance enforcement, reproducible
   run manifests, the Postgres backend, and documentation matching reality.
   Recorded in `docs/Architecture.md`, `docs/adr/ADR-002`, `docs/DecisionLog.md`.
4. **Enrichment + validation + dataset** — SEC submissions, SEC Form ADV/IAPD, and
   constructed-domain website verification; firm-type classification against a
   written inclusion standard; validated dataset (55 at first release; 61 after the
   later website-verified single-family expansions); gold-set evaluation to measure
   the classifier. Artifacts: `data/final/`, `docs/Validation.md`,
   `docs/evidence/firmtype-goldset-eval.json`.
5. **Micro-RAG + deploy** — hybrid retrieval (semantic + BM25 + metadata including a
   numeric AUM filter), grounding/abstention control in code rather than in a
   prompt, a non-technical UI, and a free-tier public URL.
   `src/fointel/rag/`, `docs/evidence/rag-abstention-eval.md`.
6. **Deep commercial intelligence** — SEC Form 13F parsing for principal (signatory)
   + AUM (13(f) value) + recent investments; investment theses from firm websites;
   SEC bulk Form ADV (Item 5.F total AUM + Schedule A owner-principal) for
   registered non-13F firms; a duplicate that reached the delivered file was fixed
   through the pipeline, not by hand. `docs/DecisionLog.md` (D17–D24),
   `docs/KnownLimitations.md`.
7. **Adversarial hardening + live deploy** — fixes evidenced by commits and tests:
   top-k answer padding, an abstention hole on domain-word queries, unreliable
   website AUM, stale-filing principal/AUM, a 512 MB OOM at container startup
   (embedding precompute moved to build time), and free-tier host churn. The live
   URL was verified end-to-end. `docs/evidence/live-url-query-transcript.md`.

## Recorded engineering decisions (not personal claims)

The decisions below are **recorded in the repository** and enforceable from it; they
are stated here without attributing them to any person:

- The **inclusion standard** (what qualifies as a family office, what evidence is
  required) — a policy the pipeline enforces. `config/inclusion_standard.md`,
  `docs/DecisionLog.md`.
- The **precision-over-recall decision**: reject rather than guess. The gold set
  shows a **0% false-positive rate** at the cost of recall — the tradeoff is
  deliberate and measured in `docs/Validation.md`.
- The **honest scarcity finding**: rather than manufacture source diversity to hit a
  number, discovery was widened and the free-tier verifiable universe was *measured*
  and documented quantitatively. `docs/KnownLimitations.md`.
- The **freshness + source-trust rules on deep data**: use 13F/ADV facts only from
  recent filings; every shipped value is authoritative and dated. `docs/DecisionLog.md`.
- **What was not shipped** (recorded, not claimed): SMTP email-probing, synthesised
  principal emails/LinkedIn (recorded as `could_not_verify`), Wikipedia-as-
  verification, website-scraped AUM, guessed values dressed as verified, and any
  record that failed a gate. `docs/Validation.md`, `docs/KnownLimitations.md`.
- Every AI-assisted output was checked against reality — APIs probed live, records
  spot-checked, claims reconciled with artifacts, and a gate review + adversarial
  pass run to find weaknesses before a reviewer would. `docs/evidence/`,
  `docs/ValidationChains.md`.

## Known limitations (not hidden)

Principal/AUM depth is bounded to firms that file 13F or an ADV (the principal is a
signatory/control person, AUM is 13(f)- or ADV-basis — disclosed per record);
discovery is SEC-heavy though every record is multi-source *verified*; some types
are honestly Undetermined; contact fields free sources don't expose (LinkedIn, work
email) are honest `could_not_verify`; the RAG dataset is intentionally small and
validated. All are documented in `KnownLimitations.md`.

## Human-judgment items (assigned, not auto-filled)

Anything requiring human judgment — reviewing the machine-drafted gold set, final
verification of disputed records, or confirming effort figures — is **assigned to the
candidate** and is not fabricated in this repository. See
[goldset/review_worksheet.md](../goldset/review_worksheet.md) and
[docs/effort-report.md](docs/effort-report.md).
