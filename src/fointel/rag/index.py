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
    if r.principal_name:
        parts.append("Principal: " + r.principal_name
                     + (f", {r.principal_title}" if r.principal_title else ""))
    for sig in r.signals:
        parts.append("Recent activity: " + sig.text)
    return " | ".join(parts)


_AUM_UNIT = {"billion": 1e9, "b": 1e9, "million": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}


def parse_aum_usd(aum_text: Optional[str]) -> Optional[int]:
    """Extract the leading dollar figure from an AUM string ('$228.5M in 13(f)...',
    '$5 billion') as a USD integer, for numeric filtering. None if unparseable."""
    if not aum_text:
        return None
    m = re.search(r"\$\s*([\d,.]+)\s*(billion|million|thousand|b|m|k)?", aum_text, re.I)
    if not m:
        return None
    try:
        num = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return int(num * _AUM_UNIT.get((m.group(2) or "").lower(), 1))


def record_meta(r: FamilyOfficeRecord) -> dict:
    return {
        "fo_type": r.fo_type.value,
        "hq_state": (r.hq_state or "").upper(),
        "hq_country": r.hq_country or "",
        "confidence": r.record_confidence.value,
        "sectors": [s.lower() for s in r.investing_sectors],
        "aum_usd": parse_aum_usd(r.estimated_aum),
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
    """Extract hard structured filters from a natural-language query: family-office
    type, US state, and a numeric AUM constraint (e.g. 'AUM over $500M')."""
    q = query.lower()
    filters: dict = {}
    if re.search(r"single[- ]family|\bsfos?\b", q):
        filters["fo_type"] = "Single-Family Office"
    elif re.search(r"multi[- ]family|\bmfos?\b", q):
        filters["fo_type"] = "Multi-Family Office"
    for name, abbr in US_STATES.items():
        if re.search(rf"\b{name}\b", q):
            filters["hq_state"] = abbr
            break
    filters.update(_parse_aum_filter(q))
    return filters


def _parse_aum_filter(q: str) -> dict:
    """Read an AUM threshold + direction, e.g. 'AUM over $500m', 'more than $1 billion',
    'under $250 million'. Returns {'aum_min': n} or {'aum_max': n} (USD), else {}."""
    m = re.search(
        r"(over|above|more than|greater than|at least|north of|min(?:imum)?|>=?|"
        r"under|below|less than|smaller than|max(?:imum)?|<=?)\s*"
        r"\$?\s*([\d.,]+)\s*(billion|million|thousand|b|m|k)\b", q, re.I)
    if not m:
        return {}
    try:
        val = int(float(m.group(2).replace(",", "")) * _AUM_UNIT.get(m.group(3).lower(), 1))
    except ValueError:
        return {}
    op = m.group(1).lower()
    lo = any(w in op for w in ("over", "above", "more", "greater", "least", "north", "min", ">"))
    return {"aum_min": val} if lo else {"aum_max": val}
