"""
Retrieval index — the data layer for the RAG.

Each record becomes (a) a text document for semantic + keyword retrieval and
(b) a metadata dict for structured filtering. Embeddings use fastembed (ONNX,
no torch) so the deployed image stays small and needs no API key. The three
retrieval legs (vector / BM25 / metadata) are fused in `retrieve.py`.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
from rank_bm25 import BM25Okapi

from ..observability import get_logger
from ..schema import FamilyOfficeRecord

log = get_logger("retrieval")

EMBED_MODEL = "BAAI/bge-small-en-v1.5"   # 384-dim, fastembed-supported, small
# Precomputed document vectors (built at image build time) let the runtime load vectors
# instead of running the ONNX model at startup — avoids the startup memory spike that
# OOM-kills a 512 MB free instance. The model then loads lazily only on the first query.
DOC_EMBEDDINGS_PATH = os.getenv("DOC_EMBEDDINGS_PATH", "data/final/doc_embeddings.npz")

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

# Country aliases -> the canonical hq_country string used in the dataset. Enables
# country queries (now that the set includes international offices, e.g. Belgium,
# Denmark, France). An unknown country simply yields no matches -> honest abstention.
COUNTRIES = {
    "united states": "United States", "usa": "United States", "u.s.": "United States",
    "u.s.a.": "United States", "america": "United States",
    "belgium": "Belgium", "france": "France", "denmark": "Denmark", "germany": "Germany",
    "switzerland": "Switzerland", "monaco": "Monaco", "brazil": "Brazil",
    "united kingdom": "United Kingdom", "uk": "United Kingdom", "canada": "Canada",
    "singapore": "Singapore", "netherlands": "Netherlands", "luxembourg": "Luxembourg",
    "spain": "Spain", "nigeria": "Nigeria",
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


def focus_text(r: FamilyOfficeRecord) -> str:
    """The record's TOPICAL evidence only — thesis, sectors, and recent 13F holdings.

    Embedded as a second, undiluted channel: in the full document these fragments are
    averaged away by the generic family-office prose every record shares, so topical
    queries ("family offices investing in healthcare") rank on prose richness instead
    of actual holdings. Scored separately, "New 13F positions: Abbvie Inc, Merck & Co"
    can match a healthcare query on its own. Empty string when a record carries no
    topical evidence (its row is zeroed — it simply doesn't compete on this channel)."""
    parts = []
    if r.investment_thesis:
        parts.append(r.investment_thesis)
    if r.investing_sectors:
        parts.append("Invests in sectors: " + ", ".join(r.investing_sectors))
    for sig in r.signals:
        parts.append("Recent investments: " + sig.text)
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


def embed_focus(records, model_name: str = EMBED_MODEL) -> np.ndarray:
    """Embed each record's focus_text; rows with no topical evidence are zeroed so they
    score 0 on the focus channel instead of matching on an empty-string artifact."""
    texts = [focus_text(r) for r in records]
    arr = embed_texts([t or " " for t in texts], model_name)
    for i, t in enumerate(texts):
        if not t:
            arr[i] = 0.0
    return arr


def precompute_and_save(records, path: str = DOC_EMBEDDINGS_PATH) -> tuple:
    """Embed every record's full document AND its topical focus channel; save both
    matrices to `path` (.npz). Run at image build time so the deployed runtime loads
    vectors instead of running the model at startup (the startup model+batch spike is
    what OOM-kills a 512 MB instance)."""
    docs = embed_texts([record_text(r) for r in records])
    focus = embed_focus(records)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    np.savez(path if path.endswith(".npz") else path + ".npz", docs=docs, focus=focus)
    return docs.shape, focus.shape


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
            # injected (tests, no model): the focus channel stays inert (all-zero rows)
            self.embeddings = embeddings
            self.focus = np.zeros_like(embeddings)
        else:
            self.embeddings, self.focus = self._load_or_embed()

    def _load_or_embed(self) -> tuple[np.ndarray, np.ndarray]:
        """Load precomputed doc+focus vectors if present and shaped to match; else embed
        now. Loading avoids importing/running the ONNX model at startup (memory)."""
        if os.path.exists(DOC_EMBEDDINGS_PATH):
            try:
                z = np.load(DOC_EMBEDDINGS_PATH)
                docs, focus = z["docs"], z["focus"]
                if docs.ndim == 2 and docs.shape[0] == len(self.docs) > 0 \
                        and focus.shape == docs.shape:
                    log.info("loaded precomputed doc embeddings", extra={
                        "event": "embeddings_loaded", "count": int(docs.shape[0])})
                    return docs.astype(np.float32), focus.astype(np.float32)
            except Exception as exc:
                log.warning("precomputed embeddings unusable; embedding at runtime", extra={
                    "event": "embeddings_fallback", "error": str(exc)})
        return embed_texts(self.docs, self.model_name), embed_focus(self.records, self.model_name)

    def embed_query(self, query: str) -> np.ndarray:
        return embed_texts([query], self.model_name)[0]


# --- query parsing (structured retrieval signal) ------------------------- #

# Type intent, robust to how users actually phrase it: "single-family", "single family
# offices", "single office families", "SFO" — and the multi equivalents.
_TYPE_SFO = re.compile(r"\bsingle[\s-]*(famil(y|ies)|offices?)\b|\bsfos?\b", re.I)
_TYPE_MFO = re.compile(r"\bmulti[\s-]*(famil(y|ies)|offices?)\b|\bmfos?\b", re.I)

# Two-letter state abbreviations that are ALSO common English words match only when the
# user typed them in UPPERCASE ("offices in IN" stays unfiltered unless written "IN").
_AMBIGUOUS_ABBR = {"IN", "OR", "ME", "OK", "HI", "DE", "OH", "PA", "MA", "AL", "LA",
                   "ID", "CO", "MT", "MS", "VA"}


def parse_filters(query: str) -> dict:
    """Extract hard structured filters from a natural-language query: family-office
    type, US state (full name, spacing-tolerant, or abbreviation), and a numeric AUM
    constraint (e.g. 'AUM over $500M')."""
    q = query.lower()
    filters: dict = {}
    if _TYPE_SFO.search(q):
        filters["fo_type"] = "Single-Family Office"
    elif _TYPE_MFO.search(q):
        filters["fo_type"] = "Multi-Family Office"
    # full state names first (spacing/hyphen tolerant: "new york" / "newyork" / "new-york")
    for name, abbr in US_STATES.items():
        if re.search(r"\b" + name.replace(" ", r"[\s-]?") + r"\b", q):
            filters["hq_state"] = abbr
            break
    # then abbreviations ("family offices in NY"); ambiguous ones require uppercase
    if "hq_state" not in filters:
        for tok in re.findall(r"\b[A-Za-z]{2}\b", query):
            up = tok.upper()
            # ambiguous abbrevs need deliberate uppercase — and an ALL-CAPS query makes
            # every word uppercase, so it signals nothing ("TELL ME ABOUT..." != Maine)
            if up in US_STATES.values() and (up not in _AMBIGUOUS_ABBR
                                             or (tok.isupper() and not query.isupper())):
                filters["hq_state"] = up
                break
    if "hq_state" not in filters:      # a US state is more specific than a country
        for alias, canon in COUNTRIES.items():
            if re.search(rf"\b{re.escape(alias)}\b", q):
                filters["hq_country"] = canon
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
