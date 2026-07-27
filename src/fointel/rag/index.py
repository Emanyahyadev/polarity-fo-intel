"""
Retrieval index — the data layer for the RAG.

Each record becomes (a) a text document for semantic + keyword retrieval and
(b) a metadata dict for structured filtering. Embeddings use fastembed (ONNX,
no torch) so the deployed image stays small and needs no API key. The three
retrieval legs (vector / BM25 / metadata) are fused in `retrieve.py`.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

import numpy as np
from rank_bm25 import BM25Okapi

from ..schema import FamilyOfficeRecord

EMBED_MODEL = "BAAI/bge-small-en-v1.5"   # 384-dim, fastembed-supported, small

US_STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA",
    "kansas": "KS", "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}


def record_text(r: FamilyOfficeRecord) -> str:
    parts = [r.name, r.fo_type.value]
    if r.description:
        parts.append(r.description)
    if r.investment_thesis:
        parts.append(r.investment_thesis)
    if r.investing_sectors:
        parts.append("Sectors: " + ", ".join(r.investing_sectors))
    loc = ", ".join(x for x in [r.hq_city, r.hq_state, r.hq_country] if x)
    if loc:
        parts.append("Location: " + loc)
    if r.estimated_aum:
        parts.append("AUM: " + r.estimated_aum)
    for sig in r.signals:
        parts.append("Recent: " + sig.text)
    return " | ".join(parts)


def record_meta(r: FamilyOfficeRecord) -> dict:
    return {
        "fo_type": r.fo_type.value,
        "hq_state": (r.hq_state or "").upper(),
        "hq_country": r.hq_country or "",
        "confidence": r.record_confidence.value,
        "sectors": [s.lower() for s in r.investing_sectors],
    }


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


@lru_cache(maxsize=2)
def _embedder(model_name: str):
    from fastembed import TextEmbedding
    return TextEmbedding(model_name)


def embed_texts(texts: list[str], model_name: str = EMBED_MODEL) -> np.ndarray:
    if not texts:
        return np.zeros((0, 384), dtype=np.float32)
    vecs = np.array(list(_embedder(model_name).embed(texts)), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


class RetrievalIndex:
    """Holds records + their documents, metadata, BM25, and (optionally) embeddings.

    Pass `embeddings=` to inject vectors in tests without loading a model.
    """

    def __init__(self, records: list[FamilyOfficeRecord],
                 embeddings: Optional[np.ndarray] = None, model_name: str = EMBED_MODEL):
        self.records = records
        self.model_name = model_name
        self.docs = [record_text(r) for r in records]
        self.meta = [record_meta(r) for r in records]
        self.bm25 = BM25Okapi([tokenize(d) for d in self.docs]) if records else None
        if embeddings is not None:
            self.embeddings = embeddings
        else:
            self.embeddings = embed_texts(self.docs, model_name)

    def embed_query(self, query: str) -> np.ndarray:
        return embed_texts([query], self.model_name)[0]


# --- query parsing (structured retrieval signal) ------------------------- #

def parse_filters(query: str) -> dict:
    """Extract hard filters from a natural-language query (type, state, country)."""
    q = query.lower()
    filters: dict = {}
    if re.search(r"single[- ]family|\bsfo\b", q):
        filters["fo_type"] = "Single-Family Office"
    elif re.search(r"multi[- ]family|\bmfo\b", q):
        filters["fo_type"] = "Multi-Family Office"
    for name, abbr in US_STATES.items():
        if re.search(rf"\b{name}\b", q):
            filters["hq_state"] = abbr
            break
    return filters
