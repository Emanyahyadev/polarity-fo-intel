"""
fointel — Family Office Intelligence pipeline.

A production-shaped system that discovers, enriches, validates, and serves a
decision-grade dataset of family offices, then exposes it through a grounded
Micro-RAG.

Layer map (see docs/Architecture.md):
    discovery/   -> production system: find candidate family offices (multi-source)
    enrichment/  -> production system: fill entity / principal / signal cells
    validation/  -> validation layer: prove trustworthiness (gold set, FP/FN, gating)
    store/       -> data layer: structured store (SQLite) + semantic index
    rag/         -> retrieval + grounded generation (code-enforced abstention)
    serve/       -> presentation layer: API + non-technical UI

The two rules of proof this system enforces:
    Rule 1 (cell): every high-value value carries provenance (source + method).
    Rule 2 (firm): a record only qualifies when the firm is affirmatively an FO.
"""

__version__ = "0.1.0"
