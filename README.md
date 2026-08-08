# Polarity FO Intel

A production-shaped pipeline that discovers, enriches, and **validates** a decision-grade dataset of 61 family offices, then serves it through a grounded Micro-RAG with a non-technical, customer-facing UI.

Built for the PolarityIQ Differentiator, Stage 1, Task 1.

**▶ Live demo:** **https://family-office-intelligence.onrender.com** — try *"multi-family offices in Texas"*, *"single-family offices in Belgium"*, or *"Tell me about Pathstone"*. Ask something off-topic (*"best pizza in Chicago"*) and it declines instead of guessing. *(Hosted on a free tier and kept warm; a rare first request after idle may take a few seconds.)*

## The idea in one line
A fund manager opens a URL, asks *"multi-family offices in Texas"*, and gets an answer **grounded in verified records** — or an honest "not enough evidence."

## Deliverables (assessment map)
| Deliverable | Where |
|---|---|
| Dataset — 80 validated records (25 Medium / 55 Low confidence; 10 Single-Family, 15 Multi-Family, 55 Undetermined) | `data/final/family_offices.xlsx` / `.csv` |
| Methodology | [docs/Methodology.md](docs/Methodology.md) |
| Validation + gold-set metrics (precision 1.00, FP-rate 0.00 · recall 0.50, accuracy 0.68, 8 FNs · system recall 0.75) | [docs/Validation.md](docs/Validation.md) |
| 3 validation chains | [docs/ValidationChains.md](docs/ValidationChains.md) |
| Micro-RAG (hybrid retrieval + code-enforced grounding) | `src/fointel/rag/`, [eval](docs/evidence/rag-abstention-eval.md) |
| **Live customer-facing URL** | **https://family-office-intelligence.onrender.com** ([Deployment](docs/Deployment.md), [live transcript](docs/evidence/live-url-query-transcript.md)) |
| Discovery report (398 → 61, with rejections) | `docs/evidence/dataset-discovery-report.json` |
| Build session summary | [docs/BuildSessionSummary.md](docs/BuildSessionSummary.md) |
| Task 2 — SaaS conversion analysis | [docs/Task2_SaaS_Conversion.md](docs/Task2_SaaS_Conversion.md) |
| Reproducibility (run manifests, content-hash snapshots) | `docs/evidence/run-manifest-*.json` |

## Deep intelligence (commercial value)
Beyond firm identity + contact, records that file **SEC Form 13F** carry authoritative, dated **principal** (name + title + direct phone, from the filing's signature block), **AUM** (aggregate 13(f) securities value), and **recent investments** (new positions vs the prior quarter) — ~25/61. **Investment thesis** (~24/61) is an attributable quote from the firm's own site. Everything unverifiable from a free authoritative source — corporate/principal LinkedIn, work email, and (for non-13F firms) principal/AUM — is honest `could_not_verify`, never guessed. See [KnownLimitations](docs/KnownLimitations.md) for the exact coverage and caveats (the principal is the 13F *signatory*; AUM is 13(f) securities, not total).

## Micro-RAG
Layered: `rag/index` (fastembed/ONNX embeddings — no torch — in **two semantic channels**: the full document plus an undiluted **topical focus channel** (thesis + sectors + 13F holdings), + BM25 + metadata inc. **numeric AUM filter**) · `rag/retrieve` (RRF-fused hybrid; a channel only awards rank credit where it has signal, and a record scores as its best semantic channel — so "family offices that invest in healthcare" ranks on actual holdings, not prose similarity) · `rag/ground` (**code-enforced** abstention below a tuned similarity threshold + verifies generated answers only name retrieved firms) · `rag/answer` (Groq LLM if a key is set, else deterministic extractive; both bounded by grounding) · `serve` (FastAPI + non-technical UI). Structured *and* semantic in one query — *"multi-family offices with AUM over $1 billion"* filters type+AUM then ranks semantically; answers surface principal, AUM, and recent investments. Reads the committed deliverable CSV, so answers are reproducibly grounded. Abstention/grounding eval: **29/29** — declines plain off-topic (pizza/weather/bitcoin) *and* adversarial in-vocabulary probes ("best pizza **office** in chicago", "family offices headquartered on the **moon**") that borrow domain words to inflate similarity. Specific queries return only above-threshold matches (no top-k padding). Architecture diagram: [`docs/rag-architecture.html`](docs/rag-architecture.html). Run locally:
```bash
uvicorn fointel.serve.app:app --port 8000    # then open http://localhost:8000
```

## What makes the dataset trustworthy
- **Rule 1 (cells):** every high-value value carries provenance (source + method + confidence).
- **Rule 2 (firms):** a firm counts toward the 61 only with affirmative evidence it *is* a family office; SFO/MFO/Undetermined is labelled honestly, never relabelled.
- **Findings govern releases:** anything that fails validation is withheld from delivered fields and recorded in an audit trail.
- **Multi-source & independent:** the delivered set is discovered via SEC EDGAR (13F, 28), SEC IAPD / Form ADV registration (20), and a curated Wikipedia/Wikidata reference lens (13); every fact is *verified* against an authoritative source of a **different class than discovery** (51/61), never one source copied at scale. (SEC dominates free-tier US discovery — an honest, disclosed skew.)

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
