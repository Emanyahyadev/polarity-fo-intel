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
        elif key == "hq_country":
            if (meta.get("hq_country") or "").lower() != value.lower():
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
    # focus channel: the record's topical evidence (thesis/sectors/13F holdings) embedded
    # undiluted, so "investing in healthcare" can rank on actual holdings instead of the
    # generic family-office prose every record shares. Zero rows (no topical evidence)
    # simply don't compete on this channel.
    fscores = {i: float(index.focus[i] @ qv) for i in allowed}
    bm = index.bm25.get_scores(tokenize(query))
    bscores = {i: float(bm[i]) for i in allowed}

    # A channel only awards rank credit where it actually has signal: BM25 zeros and
    # zero focus rows are EXCLUDED from their rank lists. (Ranking ties-at-zero used to
    # hand arbitrary records nearly the same credit as a genuine keyword match — for a
    # firm-name query, every irrelevant record got ~1/(k+1) BM25 credit "for free".)
    v_rank = {i: r for r, i in enumerate(sorted(allowed, key=lambda i: vscores[i], reverse=True))}
    b_hits = [i for i in allowed if bscores[i] > 0.0]
    b_rank = {i: r for r, i in enumerate(sorted(b_hits, key=lambda i: bscores[i], reverse=True))}
    focussed = [i for i in allowed if fscores[i] > 0.0]
    f_rank = {i: r for r, i in enumerate(sorted(focussed, key=lambda i: fscores[i], reverse=True))}

    def fused(i: int) -> float:
        s = 1.0 / (rrf_k + v_rank[i])
        if i in b_rank:
            s += 1.0 / (rrf_k + b_rank[i])
        if i in f_rank:
            s += 1.0 / (rrf_k + f_rank[i])
        return s

    ranked = sorted(allowed, key=fused, reverse=True)[:top_k]
    # a record is as relevant as its BEST semantic channel — grounding and the displayed
    # match score both use max(full-document, focus) similarity
    return [Retrieved(record=index.records[i], vector_score=max(vscores[i], fscores[i]),
                      bm25_score=bscores[i], rrf=fused(i)) for i in ranked]
