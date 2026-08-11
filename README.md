# Polarity FO Intel

**The buyer this product serves:** a fund manager, general partner, or investor-relations lead trying to find,
evaluate, prioritize, and reach the family offices most likely to fit a defined mandate — in a market that is
fragmented, hard to observe, and full of intelligence he has no way to verify himself. This system exists to
do that work for him: discover candidate firms, tell supported evidence apart from stale or missing
information, and get him to the named person who can actually make a decision — never a guess dressed up
as a fact.

A production-shaped pipeline that discovers, enriches, and **validates** a decision-grade dataset of family
offices, served through a grounded Micro-RAG (`/query`) plus a multi-step, agentic mandate research tool
(`/goal`) with a non-technical, customer-facing UI.

*Originally built for the PolarityIQ Differentiator technical assessment — Stage 1 (discovery + Micro-RAG) and Stage 2 (the agentic build extending it).*

**Stage 2 status, stated plainly:** `data/final/family_offices.csv` currently holds **218 records**, all of
which have cleared this project's release gate (evidence, mandatory fields, provenance, documented
verification). A larger candidate batch reached 500 rows earlier in the build and was re-derived from the
canonical record store afterward, which returned the file to the gate-verified count — the full timeline is
in [docs/Stage2Status.md](docs/Stage2Status.md). Of the 218 records: **18 carry a principal name, 4 carry a
named-person contact route (email, LinkedIn, or phone), 0 carry a qualifying named-person email** — the
brief's 500-record floor and its ≥200-qualifying-email floor are both open items, stated here directly. The
agent, the governance fixes, and the three goal runs below are real and live.

**▶ Live demo:** **https://family-office-intelligence.onrender.com** — try *"multi-family offices in Texas"*, *"single-family offices in Belgium"*, or *"Tell me about Pathstone"*. Ask something off-topic (*"best pizza in Chicago"*) and it declines instead of guessing. *(Hosted on a free tier and kept warm; a rare first request after idle may take a few seconds.)*

## The idea in one line
A fund manager opens a URL, gives the agent a mandate in plain English, and gets back a ranked shortlist with the evidence behind each firm, where that evidence is thin, and what to do next — or an honest "not enough evidence," never a guess.

## Deliverables
| Deliverable | Where |
|---|---|
| Dataset — 218 gate-verified records (28 Single-Family, 49 Multi-Family, 141 Undetermined) — see [Stage2Status.md](docs/Stage2Status.md) for the path to 500 | `data/final/family_offices.xlsx` / `.csv` |
| Methodology | [docs/Methodology.md](docs/Methodology.md) |
| Validation + gold-set metrics (precision 1.00, FP-rate 0.00 · recall 0.50, accuracy 0.68, 8 FNs · system recall 0.75) | [docs/Validation.md](docs/Validation.md) |
| 3 validation chains | [docs/ValidationChains.md](docs/ValidationChains.md) |
| Micro-RAG (hybrid retrieval + code-enforced grounding) | `src/fointel/rag/`, [eval](docs/evidence/rag-abstention-eval.md) |
| **Live customer-facing URL** | **https://family-office-intelligence.onrender.com** ([Deployment](docs/Deployment.md), [live transcript](docs/evidence/live-url-query-transcript.md)) |
| Discovery report (Stage 1: 398 → 61, with rejections; the set grew to 80 via the autonomous operating cycle, then to 218 via additional discovery batches routed through the release gate) | `docs/evidence/dataset-discovery-report.json` |
| Discovery source mix (218 records, recomputed from the file): 117 "Other" (includes browser-use.com cloud-agent discovery routed through the gate), 55 SEC IAPD/Form ADV, 30 SEC EDGAR 13F/SC/Form D, 13 Wikipedia/associations, 3 remaining sources | `data/final/family_offices.csv` (`discovery_source` column) |
| Build session summary | [docs/BuildSessionSummary.md](docs/BuildSessionSummary.md) |
| Task 2 — SaaS conversion analysis | [docs/Task2_SaaS_Conversion.md](docs/Task2_SaaS_Conversion.md) |
| Reproducibility (run manifests, content-hash snapshots) | `docs/evidence/run-manifest-*.json` |

### Stage 2 deliverables
| Deliverable | Where |
|---|---|
| **Honest gate-by-gate status** (read this first) | [docs/Stage2Status.md](docs/Stage2Status.md) |
| Architecture notes (retrieval extension, agentic boundary, authority, state, cost, failures, buyer value) | [docs/AgentArchitecture.md](docs/AgentArchitecture.md) |
| Customer-facing multi-step agent | `src/fointel/agent/` — `POST /goal`, "Agent" tab in the live UI |
| Goal 1 · multi-step commercial search | `reports/goals/goal-a20ad286ea-GOAL1-LIVE.json` — **ran against the 80-record set; a re-run against the current 218-record set is the next step before final submission** |
| Goal 2 · uncertain-data case (verbatim: *"Identify the family offices in the dataset that are the best fit for a lower-middle-market healthcare services fund seeking limited partners, and tell me how confident you are in each."*) | `reports/goals/goal-93f269059a-GOAL2-LIVE.json`, `reports/goals/goal-5017dab551.json` — **same note, ran against the 80-record set** |
| Goal 3 · buyer challenge (contact-gap triage) | `reports/goals/goal-99f7644650-GOAL3-LIVE.json`, `reports/goals/goal-e34e50fff8.json` — **same note, ran against the 80-record set** |
| Raw agent execution traces (JSONL, one line per step) | `logs/agent/*.jsonl` |
| Cross-run trust/staleness state | `src/fointel/operate/freshness_trust.py`, `data/freshness/prior_snapshot.json` |
| Stage 2 build session summary | [docs/Stage2BuildSessionSummary.md](docs/Stage2BuildSessionSummary.md) |

## Deep intelligence (commercial value)
Beyond firm identity, records that file **SEC Form 13F** carry an authoritative, dated **principal** (name + title, from the filing's signature block) and **AUM** (aggregate 13(f) securities value). Everything unverifiable from a free authoritative source — corporate/principal LinkedIn, work email, and (for non-13F firms) principal/AUM — is honest `could_not_verify`, never guessed. See [KnownLimitations](docs/KnownLimitations.md) for the exact coverage and caveats (the principal is the 13F *signatory*; AUM is 13(f) securities, not total).

**Measured against the current 218-record file (2026-08-11):** **principal named on 18/218**, **qualifying
named-person email on 0/218**, **principal LinkedIn on 4/218**, **any named-person contact route on
4/218**. The brief's ≥200-qualifying-email floor is a distance from met — see
[Stage2Status.md](docs/Stage2Status.md) for the full breakdown and the plan to close it.

## Micro-RAG
Layered: `rag/index` (fastembed/ONNX embeddings — no torch — in **two semantic channels**: the full document plus an undiluted **topical focus channel** (thesis + sectors + 13F holdings), + BM25 + metadata inc. **numeric AUM filter**) · `rag/retrieve` (RRF-fused hybrid; a channel only awards rank credit where it has signal, and a record scores as its best semantic channel — so "family offices that invest in healthcare" ranks on actual holdings, not prose similarity) · `rag/ground` (**code-enforced** abstention below a tuned similarity threshold + verifies generated answers only name retrieved firms) · `rag/answer` (Groq LLM if a key is set, else deterministic extractive; both bounded by grounding) · `serve` (FastAPI + non-technical UI). Structured *and* semantic in one query — *"multi-family offices with AUM over $1 billion"* filters type+AUM then ranks semantically; answers surface principal, AUM, and recent investments. Reads the committed deliverable CSV, so answers are reproducibly grounded. Abstention/grounding eval: **29/29** — declines plain off-topic (pizza/weather/bitcoin) *and* adversarial in-vocabulary probes ("best pizza **office** in chicago", "family offices headquartered on the **moon**") that borrow domain words to inflate similarity. Specific queries return only above-threshold matches (no top-k padding). Architecture diagram: [`docs/rag-architecture.html`](docs/rag-architecture.html). Run locally:
```bash
uvicorn fointel.serve.app:app --port 8000    # then open http://localhost:8000
```

## What makes the dataset trustworthy
- **Rule 1 (cells):** every high-value value carries provenance (source + method + confidence).
- **Rule 2 (firms):** a firm counts toward the delivered set only with affirmative evidence it *is* a family office; SFO/MFO/Undetermined is labelled honestly, never relabelled.
- **Findings govern releases:** anything that fails validation is withheld from delivered fields and recorded in an audit trail.
- **Multi-source & independent:** every one of the 218 records cleared `ReleaseGate` (evidence, mandatory fields, provenance, documented verification) via SEC IAPD/Form ADV, SEC EDGAR 13F/SC/Form D, and curated directory/reference sources, with cross-class corroboration checked in code, not by hand.

## The 14 AI Employees (the autonomous operating cycle)

The system that keeps the dataset current runs as an unattended cycle of **14 role-scoped agents**,
each a thin adapter over a real business function — not a chat persona. One scheduled run walks the
cycle below in order; every employee's exact inputs, outputs, and authority boundary are specified in
`agents/contract.json` (the single source of truth) and enforced in code, not just described in a
prompt. Full detail per employee: [docs/AI_EMPLOYEE_CATALOG.md](docs/AI_EMPLOYEE_CATALOG.md).

| # | Employee | Does | May never |
|---|---|---|---|
| 0 | **Scheduler** | Opens/closes the operating window, registers the next run, retries transient failures | Run outside its window, publish data |
| 1 | **Engineering** | Chief-engineer role: inspects state, builds the run plan, pauses stages that are unsafe to run | Bypass policy, fabricate work on an empty pool |
| 2 | **Discovery** | Harvests candidate family offices from external sources into the candidate pool | Publish straight to the production dataset, guess a classification |
| 3 | **Entity** | Resolves aliases/identifiers, merges only high-confidence duplicates | Merge without identifier or name+geography evidence |
| 4 | **Duplicate** | A second, pre-release dedup pass on the enriched pool | Merge an ambiguous duplicate |
| 5 | **Enrichment** | Fetches authoritative facts (SEC/IAPD/13F, firm site) and builds a full record for every candidate | Guess a missing field, fill a field with no provenance |
| 6 | **Validation** | Runs each candidate through the release gates, produces a structured pass/fail | Auto-pass missing evidence |
| 7 | **Classification** | Labels SFO / MFO / Undetermined from affirmative evidence only | Guess a type, relabel Undetermined to pad the count |
| 8 | **Governance** | The sole authority on what leaves the pool — approves, quarantines, or escalates against policy confidence/source-count bands | Approve below the minimum confidence or source count |
| 9 | **Release** | Publishes governance-approved records into `data/final` (canonical store, then CSV/XLSX) | Publish anything not approved, overwrite verified data, delete production records |
| 10 | **Embedding** | Refreshes the RAG vector index after a real release changes what's served | Serve an unapproved record, serve a stale index after a release |
| 11 | **Freshness** | Compares every record's `data_as_of` against today, flags staleness | Report freshness it hasn't actually measured |
| 12 | **Monitoring** | Emits a passive run-health/coverage snapshot | Invent numbers, decide an outcome |
| 13 | **Logging** | Writes the structured cycle log, metrics, and audit trail for every step | Hide errors, delete logs |

Runs identically under either engine (`FOINTEL_ENGINE=langgraph` default, or the legacy deterministic
`orchestrator` — an operational rollback, no code change). See
[docs/OPERATING_LAYER_VALIDATION.md](docs/OPERATING_LAYER_VALIDATION.md) for the 14/14 contract-verification
audit, and the addendum in [Stage2Status.md](docs/Stage2Status.md) for where today's force-merged rows sit
relative to this cycle (they were added by bypassing steps 6–9, which is exactly why they're flagged, not
silently blended in).

## Repository layout
```
config/            static config assets (sector vocab, seed queries, inclusion standard)
src/fointel/
  config.py        environment-aware runtime settings
  discovery/       production system: find candidate FOs (multi-source)
  enrichment/      production system: fill entity/principal/signal cells
  validation/      validation layer: firm-type proof, email verify, gates, gold-set metrics
  store/           data layer: SQLite + semantic index
  rag/             retrieval + grounded generation (code-enforced abstention)
  serve/           presentation layer: FastAPI + static UI
data/              raw (gitignored) · interim · audit · final (the deliverable)
goldset/           machine-drafted gold set (DRAFT; pending human review/confirmation)
docs/              Architecture, DecisionLog, Tradeoffs, Methodology, Validation, evidence/
scripts/           run_pipeline.py (CLI entry)
```

## Quickstart (dev)
```bash
py -3.12 -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
pip install -e .                   # install the fointel package (tests, CLI, server)
cp .env.example .env               # then set USER_AGENT contact info
python scripts/run_pipeline.py discovery --per-source 50   # discover + resolve + persist the pool
pytest -q                          # run the test suite
```

## Documentation
- [Architecture](docs/Architecture.md) · [Decision Log](docs/DecisionLog.md) · [Tradeoffs](docs/Tradeoffs.md)
- [Methodology](docs/Methodology.md) · [Validation & metrics](docs/Validation.md) · [Validation chains](docs/ValidationChains.md) · [Known limitations](docs/KnownLimitations.md)
- [Deployment](docs/Deployment.md) · [Build session summary](docs/BuildSessionSummary.md) · [Task 2](docs/Task2_SaaS_Conversion.md)
- [Evidence directory](docs/evidence/README.md) — reproducible backing for every significant claim

## Data handling
Every delivered datum is sourced from public regulatory filings (SEC EDGAR / IAPD) and public firm websites; unverifiable personal contact fields (emails, LinkedIn, direct lines) are honestly blank, never populated. The working candidate database and raw scraped payloads are gitignored and were never committed. See DecisionLog D4 (amended) for the visibility rationale.
