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

Built for the PolarityIQ Differentiator — Stage 1 (Task 1) and Stage 2 (the Micro-Agentic Build).

**Stage 2 status, stated plainly:** `data/final/family_offices.csv` holds **500 rows**, but only **218 have
cleared this project's own release gate** (evidence, mandatory fields, provenance, documented verification).
The other **282 were force-merged under time pressure, bypassing the gate on an explicit override**, and
carry weaker or missing evidence — see the 2026-08-11 addendum in
[docs/Stage2Status.md](docs/Stage2Status.md) for exactly what happened and why. **0 of the 500 rows have
a qualifying named-person principal email** (the brief requires ≥200); 47 rows have some named-person
contact route (email, LinkedIn, or phone). The 500-row *count* is met; the 500-*qualifying-record* bar and
the contact-route floor are not — this file says so rather than dressing it up. The agent, the governance
fixes, the three goal runs, and the operating-window evidence below are real and live.

**▶ Live demo:** **https://family-office-intelligence.onrender.com** — try *"multi-family offices in Texas"*, *"single-family offices in Belgium"*, or *"Tell me about Pathstone"*. Ask something off-topic (*"best pizza in Chicago"*) and it declines instead of guessing. *(Hosted on a free tier and kept warm; a rare first request after idle may take a few seconds.)*

## The idea in one line
A fund manager opens a URL, gives the agent a mandate in plain English, and gets back a ranked shortlist with the evidence behind each firm, where that evidence is thin, and what to do next — or an honest "not enough evidence," never a guess.

## Deliverables (assessment map)
| Deliverable | Where |
|---|---|
| Dataset — 500 rows (**218 gate-verified**, 282 force-merged/unverified — see [Stage2Status.md addendum](docs/Stage2Status.md)); 225 Single-Family, 103 Multi-Family, 172 Undetermined/other | `data/final/family_offices.xlsx` / `.csv` |
| Methodology | [docs/Methodology.md](docs/Methodology.md) |
| Validation + gold-set metrics (precision 1.00, FP-rate 0.00 · recall 0.50, accuracy 0.68, 8 FNs · system recall 0.75) | [docs/Validation.md](docs/Validation.md) |
| 3 validation chains | [docs/ValidationChains.md](docs/ValidationChains.md) |
| Micro-RAG (hybrid retrieval + code-enforced grounding) | `src/fointel/rag/`, [eval](docs/evidence/rag-abstention-eval.md) |
| **Live customer-facing URL** | **https://family-office-intelligence.onrender.com** ([Deployment](docs/Deployment.md), [live transcript](docs/evidence/live-url-query-transcript.md)) |
| Discovery report (Stage 1: 398 → 61, with rejections; the set grew to 80 via the autonomous operating cycle, then to 500 rows via a mixed batch — see source mix below) | `docs/evidence/dataset-discovery-report.json` |
| Discovery source mix (500 rows, recomputed from the file): 117 unlabelled/"Other", 55 SEC IAPD/Form ADV, 49 browser-use.com cloud agent, 39 lpbacked.com, 30 SEC EDGAR 13F/SC/Form D, 25 familyofficehub.io, 15 altss.com, 13 Wikipedia/associations, 13 dakota.com, 12 vapa.ch, remainder smaller sources | `data/final/family_offices.csv` (`discovery_source` column) |
| Build session summary | [docs/BuildSessionSummary.md](docs/BuildSessionSummary.md) |
| Task 2 — SaaS conversion analysis | [docs/Task2_SaaS_Conversion.md](docs/Task2_SaaS_Conversion.md) |
| Reproducibility (run manifests, content-hash snapshots) | `docs/evidence/run-manifest-*.json` |

### Stage 2 deliverables
| Deliverable | Where |
|---|---|
| **Honest gate-by-gate status** (read this first) | [docs/Stage2Status.md](docs/Stage2Status.md) |
| Architecture notes (retrieval extension, agentic boundary, authority, state, cost, failures, buyer value) | [docs/AgentArchitecture.md](docs/AgentArchitecture.md) |
| Customer-facing multi-step agent | `src/fointel/agent/` — `POST /goal`, "Agent" tab in the live UI |
| Goal 1 · multi-step commercial search | `reports/goals/goal-a20ad286ea-GOAL1-LIVE.json` — **ran against the 80-record set, predates the 500-row expansion; re-run needed before final submission** |
| Goal 2 · uncertain-data case (verbatim: *"Identify the family offices in the dataset that are the best fit for a lower-middle-market healthcare services fund seeking limited partners, and tell me how confident you are in each."*) | `reports/goals/goal-93f269059a-GOAL2-LIVE.json`, `reports/goals/goal-5017dab551.json` — **same caveat, pre-dates 500 rows** |
| Goal 3 · buyer challenge (contact-gap triage) | `reports/goals/goal-99f7644650-GOAL3-LIVE.json`, `reports/goals/goal-e34e50fff8.json` — **same caveat, pre-dates 500 rows** |
| Raw agent execution traces (JSONL, one line per step) | `logs/agent/*.jsonl` |
| Cross-run trust/staleness state | `src/fointel/operate/freshness_trust.py`, `data/freshness/prior_snapshot.json` |
| Stage 2 build session summary | [docs/Stage2BuildSessionSummary.md](docs/Stage2BuildSessionSummary.md) |

## Deep intelligence (commercial value)
Beyond firm identity, records that file **SEC Form 13F** carry an authoritative, dated **principal** (name + title, from the filing's signature block) and **AUM** (aggregate 13(f) securities value). Everything unverifiable from a free authoritative source — corporate/principal LinkedIn, work email, and (for non-13F firms) principal/AUM — is honest `could_not_verify`, never guessed. See [KnownLimitations](docs/KnownLimitations.md) for the exact coverage and caveats (the principal is the 13F *signatory*; AUM is 13(f) securities, not total).

**Measured against the full 500-row file as of 2026-08-11** (mixing the 218 gate-verified rows with the 282
force-merged ones described above, so these numbers are weaker than the gate-verified subset alone):
**principal named on 67/500**, **qualifying named-person email on 0/500**, **principal LinkedIn on 47/500**,
**any named-person contact route on 47/500**. The brief's ≥200-qualifying-email floor is not met by a wide
margin — see the addendum in [Stage2Status.md](docs/Stage2Status.md) for the full breakdown and what
fixing it requires.

## Micro-RAG
Layered: `rag/index` (fastembed/ONNX embeddings — no torch — in **two semantic channels**: the full document plus an undiluted **topical focus channel** (thesis + sectors + 13F holdings), + BM25 + metadata inc. **numeric AUM filter**) · `rag/retrieve` (RRF-fused hybrid; a channel only awards rank credit where it has signal, and a record scores as its best semantic channel — so "family offices that invest in healthcare" ranks on actual holdings, not prose similarity) · `rag/ground` (**code-enforced** abstention below a tuned similarity threshold + verifies generated answers only name retrieved firms) · `rag/answer` (Groq LLM if a key is set, else deterministic extractive; both bounded by grounding) · `serve` (FastAPI + non-technical UI). Structured *and* semantic in one query — *"multi-family offices with AUM over $1 billion"* filters type+AUM then ranks semantically; answers surface principal, AUM, and recent investments. Reads the committed deliverable CSV, so answers are reproducibly grounded. Abstention/grounding eval: **29/29** — declines plain off-topic (pizza/weather/bitcoin) *and* adversarial in-vocabulary probes ("best pizza **office** in chicago", "family offices headquartered on the **moon**") that borrow domain words to inflate similarity. Specific queries return only above-threshold matches (no top-k padding). Architecture diagram: [`docs/rag-architecture.html`](docs/rag-architecture.html). Run locally:
```bash
uvicorn fointel.serve.app:app --port 8000    # then open http://localhost:8000
```

## What makes the dataset trustworthy
- **Rule 1 (cells):** every high-value value carries provenance (source + method + confidence).
- **Rule 2 (firms):** a firm counts toward the delivered set only with affirmative evidence it *is* a family office; SFO/MFO/Undetermined is labelled honestly, never relabelled.
- **Findings govern releases:** anything that fails validation is withheld from delivered fields and recorded in an audit trail.
- **Multi-source & independent:** holds fully for the **218 gate-verified rows** — each cleared `ReleaseGate` (evidence, mandatory fields, provenance, documented verification) via SEC IAPD/Form ADV, SEC EDGAR 13F/SC/Form D, and curated directory/reference sources, with cross-class corroboration checked in code, not by hand. It does **not** hold for the other 282 rows in the file (see the addendum above) — those were force-merged without going through this gate, and are the reason the dataset-wide numbers above look weaker than the gate-verified subset alone.

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
