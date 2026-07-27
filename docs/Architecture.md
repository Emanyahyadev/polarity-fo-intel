# Architecture

> Status: **v0.1 — proposed for the architecture checkpoint.** This is the design under review before discovery connectors are implemented.

## 1. What this system is, and the standard it is held to

A production-shaped pipeline that produces a **decision-grade dataset of 50 family offices** and serves it through a **grounded Micro-RAG** with a non-technical, customer-facing UI.

We build to the *validation-layer* standard from **How We Work**, not the task-completion model. Every build in this repo must answer two questions, and — critically — the *right* two, because the two build types carry different evidence standards:

| Build type | "Does it work?" | "How well does it work?" | Evidence we show |
|---|---|---|---|
| **Production system** (discovery, enrichment, retrieval, serving) | runs end-to-end, correct output shape, no silent failures | throughput, failure rate on edge cases, failure modes | the system running + output + handled/unhandled failures |
| **Validation layer** (firm-type proof, email verification, grounding control) | detects the errors it was designed to detect | accuracy vs a **gold set**: false-positive & **false-negative** rate | gold set + layer output vs it + FP/FN numbers |

The validation layer carries the higher burden: a false negative (a bad value we labelled "good") ships downstream with the system's confidence behind it. We measure and report FP/FN, not throughput, for those components.

## 2. Layered architecture (separation of concerns is a scored requirement)

```
                          ┌────────────────────────── PRESENTATION ──────────────────────────┐
                          │  serve/app.py (FastAPI)  ·  serve/web/ (non-technical UI)          │
                          └───────────────▲───────────────────────────────────────────────────┘
                                          │ /query (natural language)
              ┌───────────────────────────┴──────────── RAG (retrieval + generation) ─────────┐
              │  rag/retrieve.py  structured + semantic retrieval                              │
              │  rag/ground.py    CODE-ENFORCED grounding / abstention control                 │
              │  rag/answer.py    LLM generation, bounded by ground.py                         │
              └───────────────────────────▲──────────────────────────────────────────────────┘
                                          │ reads
                          ┌───────────────┴──────────── DATA LAYER ──────────────────────────┐
                          │  store/db.py     SQLite: records, cells, provenance, audit         │
                          │  store/vectors.py  embeddings + semantic index                      │
                          └───────────────▲──────────────────────────────────────────────────┘
                                          │ writes gated, provenance-tagged records
   ┌──────── PRODUCTION SYSTEMS ──────────┴───────────┐   ┌──────────── VALIDATION LAYER ─────────────┐
   │ discovery/  find candidate FOs (multi-source)     │──▶│ validation/firm_type.py  Rule 2 proof      │
   │   sec_adv.py · irs_990pf.py · news.py             │   │ validation/email_verify.py  MX+SMTP        │
   │ enrichment/ fill entity/principal/signal cells    │   │ validation/cross_source.py  corroboration  │
   │   entity · principals · contacts · signals        │   │ validation/gates.py  release gate → audit  │
   └──────────────────────────────────────────────────┘   │ validation/goldset.py  FP/FN metrics       │
                                                           └───────────────────────────────────────────┘
   pipeline.py orchestrates: discover → enrich → validate → gate → store → index
```

**Boundaries are hard:** discovery never proves; enrichment never gates; the gate is the only thing that decides what a customer sees; presentation never talks to the store directly (only through the RAG layer). This is exactly the "separation between retrieval, data, and presentation layers" the assessment requires.

## 3. Data model (see `src/fointel/schema.py`)

The unit is `FamilyOfficeRecord`. Two rules of proof are encoded structurally:

* **Rule 1 (cell):** `provenance: dict[field -> Provenance]` gives every high-value cell a basis (source class + method + confidence + checked_at). Unverifiable values are left blank and named in `could_not_verify`.
* **Rule 2 (firm):** `qualifies()` returns true only when `fo_type ∈ {SFO, MFO}` **and** `fo_type_evidence` is present. Only qualifying records count toward the 50.
* **Findings govern releases:** failed values never sit in delivered fields; they go to `AuditEntry` rows in `data/audit/`.

Delivered file = flat CSV/XLSX via `to_delivery_row()`; full cell lineage = a separate provenance sheet via `provenance_rows()`. This keeps the customer file readable while Rule 1 stays fully auditable.

**Schema vs. the reference sample:** the provided `FO-MAX` sample is a *static firm-and-contact list* (no AUM, no SFO/MFO type, no dated signals, no per-cell provenance, no confidence). Our schema is that floor **plus**: firm-type + evidence, AUM, recent **dated** signals, per-cell provenance, confidence that dips, honest `could_not_verify` flags, and an audit trail. Those additions are exactly the "actionability + verification" the file is scored on.

## 4. Discovery strategy — diverse but manageable (4 source classes)

Single-source-at-scale is an automatic fail. We use **four genuinely different source classes** (regulatory, tax-exempt, media, curated-directory) — diversity of *lens*, not quantity of connectors. Discovery sources are kept strictly separate from *proof* sources.

| # | Source class | Lens | Role | Evidence it contributes | Known blind spot |
|---|---|---|---|---|---|
| 1 | **SEC EDGAR — Form ADV / IA filings** | regulatory | discovery + authoritative firm facts | AUM, address, phone, adviser type (strong for MFOs & registered SFOs) | pure SFOs using the family-office exclusion don't file |
| 2 | **IRS 990-PF — private foundation filings** (ProPublica Nonprofit Explorer, free API) | tax-exempt | **discovery of single-family offices** + principals | family name, trustees/officers, location, asset scale | families without a foundation, or with a differently-named one |
| 3 | **News / press** (free web search + fetch) | media | discovery of non-filing SFOs + **recent dated signals** | recent investments, commitments, hires; existence signals | firms that never appear in press |
| 4 | **FO directories / associations** (public member lists, curated listings) | curated | discovery of established FOs, esp. MFOs & named SFOs | firm existence + self-described type; a cross-check on the other lenses | paywalled directories excluded on free-tier; listing bias |

Proof/enrichment sources (never used for discovery): firm websites, LinkedIn public profiles, cross-source corroboration.

**Why each source exists** is documented per DecisionLog D2; the methodology reports the **per-record discovery-source distribution** to demonstrate real market discovery, not one source copied. Inherent blind spot we disclose: a family office with no filing, no foundation, no press, and no directory listing is invisible to all four — an honest limit of any free-tier approach.

## 4a. Discovery / verification separation (enforced in the record)

Every record carries `discovery_source` (how the firm was **found**) and a list of `verification_sources` (how facts were **proven**) as separate structures. A verification source that reuses the discovery source class raises an `independence_warning` unless a justification is recorded in `reviewer_notes`. This makes "found ≠ proven" a checkable property, not a promise.

## 4b. Field-level confidence

Confidence is per-field and **derived from the evidence** (`field_confidence()` reads each cell's provenance), so it cannot be inflated independently of its basis. `record_confidence` is the weakest link across the identity anchors (firm name + type). Commercial fields never raise it; missing evidence lowers it. Fields with their own confidence: firm name, type, principal, email, phone, website, AUM, thesis, recent activity, LinkedIn.

## 5. Validation layer (the higher-burden build)

* **Firm-type (Rule 2):** classify SFO / MFO / Undetermined with extracted evidence + confidence.
* **Email verification:** syntax → MX → SMTP probe → status (deliverable / risky / undeliverable / could_not_verify). Undeliverable is **gated out** of the delivered field and logged to audit.
* **Cross-source corroboration:** a firm fact confirmed by ≥2 independent sources raises confidence; single-source facts stay Medium/Low.

**Gold-set evaluation (reads like a production ML eval).** A **25–30 record** hand-reviewed gold set for firm-type. `validation/goldset.py` reports **accuracy, precision, recall, false-positive rate, false-negative rate, and a confusion matrix**, plus concrete **failure examples, root-cause analysis, and improvement notes** (`docs/Validation.md`). A separate small gold set of known-good/known-bad addresses measures the email checker's own FP/FN. The false-negative rate is the headline metric — a bad value we labelled "good" ships downstream with our confidence behind it.

## 5a. Release gates (no record ships unless all pass)

`validation/gates.py` runs mandatory gates; a record enters `data/final/` only if **every** one passes, else it is withheld with a logged reason:
1. Firm qualifies as a family office (Rule 2, `qualifies()`).
2. Classification evidence present.
3. Discovery documented.
4. Verification documented (≥1 independent verification source).
5. Critical contradictions resolved.
6. Mandatory fields complete (name, type, geography, ≥1 contactable or entity-intelligence path).
7. Validation status recorded.
8. Audit trail retained for any withheld value.

Rejected values never appear inside customer-facing records — they live only in the audit trail.

## 6. RAG — hybrid retrieval + the grounding control

* **Hybrid retrieval (three legs, score-fused):** (a) **vector** similarity over per-record text (local `all-MiniLM-L6-v2` embeddings, zero API cost, offline-reproducible); (b) **keyword** search (BM25 / full-text) for exact names, places, sectors; (c) **metadata filtering** (type, sector, geography, AUM band, confidence) applied as hard constraints. Results are fused (reciprocal-rank fusion) so a query like "single-family offices in Texas investing in healthcare" uses filters *and* meaning *and* keywords.
* **Grounding / abstention control (enforced in code, not prompt):** (1) if fused top score < `MIN_RETRIEVAL_SCORE`, or no records satisfy the metadata filter, the system **abstains** with a clear, non-technical message; (2) generation must cite the `fo_id`/field it used; (3) a post-generation check verifies each claim maps to a retrieved cell, else the answer is qualified or declined. Prompt instructions alone are explicitly insufficient per the assessment — this control is testable and tested with unanswerable queries.

## 7. Stack (all free-tier / public — see DecisionLog D1, D5)

Python 3.12 · **Repository interface** with a SQLite backend for dev and **Postgres/Supabase** at deploy (no business-logic change) · hybrid retrieval (local embeddings + BM25 + metadata) · FastAPI + static UI · free-tier LLM (Groq or Google Gemini) for generation only · **Hugging Face Spaces (Docker)** for the persistent public URL. Structured logging (`observability.py`) across pipeline / validation / retrieval / api / deployment channels — no silent failures.

## 8. Reproducibility

* The 50-record file is an **output of committed pipeline code**, regenerable via `scripts/run_pipeline.py` — never hand-assembled.
* Raw source pulls cached under `data/raw/` (gitignored, bulky/PII); the pipeline can rebuild them.
* Deterministic where possible; every significant claim in the docs links to an artifact in `docs/evidence/`.
* `requirements.txt` now, frozen to `requirements.lock` before submission.

## 9. Explicitly out of scope (avoiding "components for show")

No multi-agent orchestration, no graph DB, no auth/multi-tenant, no write-back CRM sync, no more than 3 discovery sources, no speculative ML models. Depth goes to the dataset and the grounding control, per the assessment's priority order: **dataset first, working functionality second, presentation third.**
