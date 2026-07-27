# Polarity FO Intel

A production-shaped pipeline that discovers, enriches, and **validates** a decision-grade dataset of 50 family offices, then serves it through a grounded Micro-RAG with a non-technical, customer-facing UI.

Built for the PolarityIQ Differentiator, Stage 1, Task 1. This README is a work-in-progress scaffold; it is completed as the build progresses.

## The idea in one line
A fund manager opens a URL, asks *"single-family offices in Texas"*, and gets an answer **grounded in verified records** — or an honest "not enough evidence."

## Deliverables (assessment map)
| Deliverable | Where |
|---|---|
| Dataset — 50 validated records (28 High confidence) | `data/final/family_offices.xlsx` / `.csv` |
| Methodology | [docs/Methodology.md](docs/Methodology.md) |
| Validation + gold-set metrics (precision 1.00, FP-rate 0.00) | [docs/Validation.md](docs/Validation.md) |
| 3 validation chains | [docs/ValidationChains.md](docs/ValidationChains.md) |
| Micro-RAG (hybrid retrieval + code-enforced grounding) | `src/fointel/rag/`, [eval](docs/evidence/rag-abstention-eval.md) |
| Live customer-facing URL | Deploy: `HF_TOKEN=… python scripts/deploy_hf.py` ([Deployment](docs/Deployment.md)) |
| Discovery report (398 → 50, with rejections) | `docs/evidence/dataset-discovery-report.json` |
| Build session summary | [docs/BuildSessionSummary.md](docs/BuildSessionSummary.md) |
| Task 2 — SaaS conversion analysis | [docs/Task2_SaaS_Conversion.md](docs/Task2_SaaS_Conversion.md) |
| Reproducibility (run manifests, content-hash snapshots) | `docs/evidence/run-manifest-*.json` |

## Micro-RAG
Layered: `rag/index` (fastembed/ONNX embeddings — no torch — + BM25 + metadata) · `rag/retrieve` (RRF-fused hybrid) · `rag/ground` (**code-enforced** abstention below a tuned similarity threshold + verifies generated answers only name retrieved firms) · `rag/answer` (Groq LLM if a key is set, else deterministic extractive; both bounded by grounding) · `serve` (FastAPI + non-technical UI). Reads the committed deliverable CSV, so answers are reproducibly grounded. Abstention/grounding eval: **10/11** (declines pizza/weather/bitcoin). Run locally:
```bash
uvicorn fointel.serve.app:app --port 8000    # then open http://localhost:8000
```

## What makes the dataset trustworthy
- **Rule 1 (cells):** every high-value value carries provenance (source + method + confidence).
- **Rule 2 (firms):** a firm counts toward the 50 only with affirmative evidence it *is* a family office; SFO/MFO/Undetermined is labelled honestly, never relabelled.
- **Findings govern releases:** anything that fails validation is withheld from delivered fields and recorded in an audit trail.
- **Multi-source discovery:** SEC EDGAR Form ADV · IRS 990-PF · News/press — three independent lenses, not one source copied.

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
goldset/           hand-labelled truth for validation metrics
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
The dataset contains real individuals' business contact data. The repository is **private** and shared with the evaluator; raw scraped payloads are gitignored. See DecisionLog D4.
