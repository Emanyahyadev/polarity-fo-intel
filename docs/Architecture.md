# Architecture

> Status: **v1.0 — Wave 1 implemented and hardened through the Architecture Gate Review.** Discovery (4 lenses), evidence-based entity resolution, the release gate (single publication authority), provenance enforcement, reproducible evidence + run manifests, and the DB-agnostic storage layer are built and tested. Enrichment, the RAG/retrieval layer (§6), and the serving/UI layer are Wave 2–3 and are described here as target design.

## 1. What this system is, and the standard it is held to

A production-shaped pipeline that produces a **decision-grade dataset of 55 family offices** and serves it through a **grounded Micro-RAG** with a non-technical, customer-facing UI.

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
* **Rule 2 (firm):** `qualifies()` returns true only when `fo_type ∈ {SFO, MFO}` **and** `fo_type_evidence` is present. Only qualifying records count toward the 55.
* **Findings govern releases:** failed values never sit in delivered fields; they go to `AuditEntry` rows in `data/audit/`.

Delivered file = flat CSV/XLSX via `to_delivery_row()`; full cell lineage = a separate provenance sheet via `provenance_rows()`. This keeps the customer file readable while Rule 1 stays fully auditable.

**Schema vs. the reference sample:** the provided `FO-MAX` sample is a *static firm-and-contact list* (no AUM, no SFO/MFO type, no dated signals, no per-cell provenance, no confidence). Our schema is that floor **plus**: firm-type + evidence, AUM, recent **dated** signals, per-cell provenance, confidence that dips, honest `could_not_verify` flags, and an audit trail. Those additions are exactly the "actionability + verification" the file is scored on.

## 4. Discovery strategy — four lenses (three active discovery + one signals)

Single-source-at-scale is an automatic fail. We use **four deliberately different lenses** — diversity of *lens*, not quantity of connectors. Discovery sources are kept strictly separate from *proof* sources.

| # | Source | Lens | Role | Evidence it contributes | Known blind spot |
|---|---|---|---|---|---|
| 1 | **SEC EDGAR** — full-text search over 13F/SC filings mentioning "family office" | regulatory | discovery + authoritative firm facts (via `data.sec.gov/submissions`) | name, CIK, business location, address, phone | pure SFOs that don't file 13F/SC |
| 2 | **IRS 990-PF** (ProPublica Nonprofit Explorer, free API) | tax-exempt | discovery of families behind private foundations | family/foundation name, EIN, city/state | most FOs are for-profit → under-represented; noisy |
| 3 | **Wikipedia `Category:Family_offices` + Wikidata `Q751314`** | curated | discovery of notable offices (heavily SFO) | firm name, country, an article for enrichment | notability bias. **Discovery-only — never verifies** |
| 4 | **GDELT** news | media | **signals-primary**: per-firm recent dated activity in enrichment; best-effort discovery | recent investments, commitments, hires | generic query is a weak *discovery* channel (documented) |

**Honest reconciliation:** lens 4 (news) yields ~0 bulk discovery — GDELT's generic "family office" query is noisy — so it is repositioned to a per-firm *signals* source. The *shipped* file is therefore discovered by three active lenses (SEC / 990-PF / curated), which comfortably clears the "not one source" bar. Google News RSS was rejected on ToS grounds.

Proof/enrichment sources (never used for discovery): firm websites, LinkedIn public profiles, cross-source corroboration. **Why each source exists** is in DecisionLog D2; the methodology reports the per-record discovery-source distribution. Inherent blind spot disclosed: a firm with no filing, no foundation, no notable listing, and no press is invisible to all four.

## 4c. Entity resolution (evidence-based, never silent)

De-duplication is delegated to `EntityResolver`, not a lossy name key. Firms merge only on a **shared strong identifier** (CIK/EIN/QID/domain) or **exact normalised name + compatible geography + no identifier conflict**; a merely similar name is flagged `possible_duplicate_kept_distinct` for review, never auto-merged (a false merge silently deletes a real firm). Every decision is logged and written to `docs/evidence/02-entity-resolution-decisions.jsonl`; cross-source discovery is captured in `discovery_sources`.

## 4a. Discovery / verification separation (enforced in the record)

Every record carries `discovery_source` (how the firm was **found**) and a list of `verification_sources` (how facts were **proven**) as separate structures. A verification source that reuses the discovery source class raises an `independence_warning` unless a justification is recorded in `reviewer_notes`. This makes "found ≠ proven" a checkable property, not a promise.

## 4b. Field-level confidence

Confidence is per-field and **derived from the evidence** (`field_confidence()` reads each cell's provenance), so it cannot be inflated independently of its basis. `record_confidence` is the weakest link across the identity anchors (firm name + type). Commercial fields never raise it; missing evidence lowers it. Fields with their own confidence: firm name, type, principal, email, phone, website, AUM, thesis, recent activity, LinkedIn.

## 5. Validation layer (the higher-burden build)

* **Firm-type (Rule 2):** classify SFO / MFO / Undetermined against `config/inclusion_standard.md`, with extracted evidence + confidence.
* **Email verification (honest by design):** syntax + MX/domain-liveness + role/pattern heuristics → status (deliverable / risky / could_not_verify). We do **not** perform SMTP RCPT probing (unreliable from free/cloud IPs and treated as abusive). Values that fail are **gated out** of the delivered field and logged to audit; unverifiable ones are honest blanks.
* **Cross-source corroboration:** a firm fact confirmed by ≥2 independent sources raises confidence; single-source facts stay Medium/Low.

**Gold-set evaluation (reads like a production ML eval).** A **25–30 record** hand-reviewed gold set for firm-type. `validation/goldset.py` reports **accuracy, precision, recall, false-positive rate, false-negative rate, and a confusion matrix**, plus concrete **failure examples, root-cause analysis, and improvement notes** (`docs/Validation.md`). A separate small gold set of known-good/known-bad addresses measures the email checker's own FP/FN. The false-negative rate is the headline metric — a bad value we labelled "good" ships downstream with our confidence behind it.

## 5a. Release gate — the single publication authority

`validation/gates.py::ReleaseGate.publish()` is the **only** path to a released record. A record ships only if **all nine** gates pass, else it is withheld with logged reasons (`release` channel). Final selection then runs `validation/selection.py` to keep the shipped file source-balanced (§5b).

| Gate | Guarantees |
|---|---|
| G1 `family_office_evidenced` | Rule 2 — affirmative FO evidence (`qualifies()`) |
| G2 `classification_evidence` | a typed SFO/MFO carries evidence |
| G3 `discovery_documented` | discovery source recorded |
| G4 `verification_documented` | ≥1 authoritative (non-discovery-only) verification source |
| G5 `verification_authoritative` | Wikipedia/Wikidata (discovery-only) can never verify |
| G6 `no_contradictions` | discovery ≠ verification (independence) unless justified |
| G7 `mandatory_fields_complete` | name + geography + ≥1 actionable/entity-intelligence path |
| G8 `provenance_complete` | Rule 1 — every populated high-value cell has a basis |
| G9 `no_rejected_values_shipped` | a value in the audit trail can never appear in any delivered field |

G9 is protected by an automated invariant test in both directions. Rejected values live only in the audit trail.

## 5b. Source-diversity selection (the shipped file)

The anti-"copy at scale" rule applies to the delivered 55, not the SEC-heavy raw pool. `select_final()` picks the final N from gate-approved records so no single **discovery** source exceeds a cap (default 40% of N), preferring higher-confidence records; if diversity is insufficient the cap is relaxed only with an explicit, logged justification (DecisionLog D18).

## 5c. Reproducibility

Every run writes a manifest (`docs/evidence/run-manifest-*.json`: git commit, schema/pipeline version, timestamps, stage counts). Retrieved source content is content-addressed (sha256 in each cell's provenance) so a claim can be reproduced or shown to have drifted (`fointel.evidence`).

## 6. RAG — hybrid retrieval + the grounding control

* **Hybrid retrieval (three legs, score-fused):** (a) **vector** similarity over per-record text (local `all-MiniLM-L6-v2` embeddings, zero API cost, offline-reproducible); (b) **keyword** search (BM25 / full-text) for exact names, places, sectors; (c) **metadata filtering** (type, sector, geography, AUM band, confidence) applied as hard constraints. Results are fused (reciprocal-rank fusion) so a query like "single-family offices in Texas investing in healthcare" uses filters *and* meaning *and* keywords.
* **Grounding / abstention control (enforced in code, not prompt):** (1) if fused top score < `MIN_RETRIEVAL_SCORE`, or no records satisfy the metadata filter, the system **abstains** with a clear, non-technical message; (2) generation must cite the `fo_id`/field it used; (3) a post-generation check verifies each claim maps to a retrieved cell, else the answer is qualified or declined. Prompt instructions alone are explicitly insufficient per the assessment — this control is testable and tested with unanswerable queries.

## 7. Stack (all free-tier / public — see DecisionLog D1, D5)

Python 3.12 · **Repository interface** with a SQLite backend for dev and **Postgres/Supabase** at deploy (no business-logic change) · hybrid retrieval (local embeddings + BM25 + metadata) · FastAPI + static UI · free-tier LLM (Groq or Google Gemini) for generation only · **Hugging Face Spaces (Docker)** for the persistent public URL. Structured logging (`observability.py`) across pipeline / validation / retrieval / api / deployment channels — no silent failures.

## 8. Reproducibility

* The 55-record file is an **output of committed pipeline code**, regenerable via `scripts/run_pipeline.py` — never hand-assembled.
* Raw source pulls cached under `data/raw/` (gitignored, bulky/PII); the pipeline can rebuild them.
* Deterministic where possible; every significant claim in the docs links to an artifact in `docs/evidence/`.
* `requirements.txt` now, frozen to `requirements.lock` before submission.

## 9. Explicitly out of scope (avoiding "components for show")

No multi-agent orchestration, no graph DB, no auth/multi-tenant, no write-back CRM sync, no more than 3 discovery sources, no speculative ML models. Depth goes to the dataset and the grounding control, per the assessment's priority order: **dataset first, working functionality second, presentation third.**
