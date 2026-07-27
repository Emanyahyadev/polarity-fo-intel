"""
Hybrid retrieval — vector similarity + BM25 keyword + metadata filtering, fused
by Reciprocal Rank Fusion. A query like "single-family offices in Texas investing
in healthcare" uses the metadata filter (type=SFO, state=TX) AND semantic meaning
AND exact keywords together.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from ..schema import FamilyOfficeRecord
from .index import RetrievalIndex, tokenize


class Retrieved(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    record: FamilyOfficeRecord
    vector_score: float      # cosine similarity (normalised embeddings)
    bm25_score: float
    rrf: float               # fused rank score


def _matches(meta: dict, filters: dict) -> bool:
    for key, value in filters.items():
        if key == "sectors":
            if not any(value in s for s in meta.get("sectors", [])):
                return False
        elif key in ("aum_min", "aum_max"):
            aum = meta.get("aum_usd")
            # unknown AUM cannot satisfy a numeric AUM constraint -> exclude (we only
            # return firms we can CONFIRM meet the threshold; no guessing).
            if aum is None:
                return False
            if key == "aum_min" and aum < value:
                return False
            if key == "aum_max" and aum > value:
                return False
        elif meta.get(key) != value:
            return False
    return True


def retrieve(index: RetrievalIndex, query: str, top_k: int = 5,
             filters: Optional[dict] = None, rrf_k: int = 60) -> list[Retrieved]:
    n = len(index.records)
    if n == 0:
        return []
    allowed = [i for i in range(n) if not filters or _matches(index.meta[i], filters)]
    if not allowed:
        return []   # a hard metadata filter with no matches -> the RAG will abstain

    qv = index.embed_query(query)
    vscores = {i: float(index.embeddings[i] @ qv) for i in allowed}
    bm = index.bm25.get_scores(tokenize(query))
    bscores = {i: float(bm[i]) for i in allowed}

    v_rank = {i: r for r, i in enumerate(sorted(allowed, key=lambda i: vscores[i], reverse=True))}
    b_rank = {i: r for r, i in enumerate(sorted(allowed, key=lambda i: bscores[i], reverse=True))}

    def fused(i: int) -> float:
        return 1.0 / (rrf_k + v_rank[i]) + 1.0 / (rrf_k + b_rank[i])

    ranked = sorted(allowed, key=fused, reverse=True)[:top_k]
    return [Retrieved(record=index.records[i], vector_score=vscores[i],
                      bm25_score=bscores[i], rrf=fused(i)) for i in ranked]
