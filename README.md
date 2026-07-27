# Polarity FO Intel

A production-shaped pipeline that discovers, enriches, and **validates** a decision-grade dataset of 50 family offices, then serves it through a grounded Micro-RAG with a non-technical, customer-facing UI.

Built for the PolarityIQ Differentiator, Stage 1, Task 1. This README is a work-in-progress scaffold; it is completed as the build progresses.

## The idea in one line
A fund manager should be able to open a URL, ask *"which single-family offices in Texas have invested in healthcare recently, and who do I contact?"*, and get an answer that is **grounded in verified records** — or an honest "not enough evidence."

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
- [Methodology](docs/Methodology.md) · [Validation & metrics](docs/Validation.md) · [Known limitations](docs/KnownLimitations.md)
- [Evidence directory](docs/evidence/README.md) — reproducible backing for every significant claim

## Data handling
The dataset contains real individuals' business contact data. The repository is **private** and shared with the evaluator; raw scraped payloads are gitignored. See DecisionLog D4.
