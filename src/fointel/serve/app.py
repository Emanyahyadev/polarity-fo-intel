"""
Presentation layer — FastAPI service for the Micro-RAG.

Separation of concerns: this layer only handles HTTP + rendering; all retrieval,
grounding, and generation live in fointel.rag. The index is built once at startup
from the committed deliverable CSV. Endpoints:

    GET  /        the customer-facing UI (non-technical)
    GET  /health  liveness + record count
    GET  /records summary rows of every verified record (powers the Directory view)
    GET  /stats   dataset coverage stats, computed live from the served records so the
                  numbers always reconcile with what the service actually answers from
    POST /query   {query} -> grounded answer + record cards (or a clear abstention)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..observability import get_logger
from ..rag.answer import answer_query
from ..rag.index import RetrievalIndex
from ..rag.load import load_records_from_csv
from ..rag.roles import principal_role

log = get_logger("api")
WEB = Path(__file__).parent / "web"
_STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    records = load_records_from_csv()
    _STATE["index"] = RetrievalIndex(records)
    _STATE["count"] = len(records)
    _STATE["rows"] = [_row(r) for r in records]
    _STATE["stats"] = _stats(records)
    log.info("index ready", extra={"event": "startup", "records": len(records)})
    yield


_VERIFY_SHORT = {  # compact labels for verification chips (full names are long)
    "SEC EDGAR (13F / SC / Form D filings)": "SEC 13F",
    "SEC IAPD / Form ADV (investment-adviser registration)": "SEC ADV",
    "Firm Website": "Website",
    "IRS 990-PF (ProPublica Nonprofit Explorer)": "IRS 990-PF",
    "Curated directory / reference (Wikipedia, associations)": "Directory",
}


def _row(r) -> dict:
    """One Directory row — the same verified fields a query card carries, no more."""
    return {
        "fo_id": r.fo_id, "name": r.name, "type": r.fo_type.value,
        "location": ", ".join(x for x in [r.hq_city, r.hq_state, r.hq_country] if x),
        "country": r.hq_country, "state": r.hq_state,
        "aum": r.estimated_aum, "website": r.website, "phone": r.hq_phone,
        "principal": (f"{r.principal_name} — {r.principal_title}"
                      if r.principal_name and r.principal_title else r.principal_name),
        "principal_role": principal_role(r.verification_sources),
        "confidence": r.record_confidence.value,
        "evidence": r.fo_type_evidence,
        "signals": [s.text for s in r.signals],
        "verification": sorted({_VERIFY_SHORT.get(v.source_class.value, v.source_class.value)
                                for v in r.verification_sources}),
        "data_as_of": r.data_as_of.isoformat(),
    }


def _stats(records) -> dict:
    """Coverage stats computed from the records the service is actually serving."""
    from collections import Counter
    n = len(records)

    def cov(pred):
        return sum(1 for r in records if pred(r))

    return {
        "records": n,
        "type": dict(Counter(r.fo_type.value for r in records)),
        "confidence": dict(Counter(r.record_confidence.value for r in records)),
        "coverage": {"aum": cov(lambda r: r.estimated_aum),
                     "principal": cov(lambda r: r.principal_name),
                     "website": cov(lambda r: r.website),
                     "signals": cov(lambda r: r.signals)},
        "countries": len({r.hq_country for r in records if r.hq_country}),
        "as_of": max(r.data_as_of for r in records).isoformat(),
    }


app = FastAPI(title="Family Office Intelligence", version="1.0.0", lifespan=lifespan)


class Query(BaseModel):
    query: str


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "records": _STATE.get("count", 0)}


@app.get("/records")
def records() -> dict:
    return {"records": _STATE.get("rows", [])}


@app.get("/stats")
def stats() -> dict:
    return _STATE.get("stats", {})


@app.post("/query")
def query(payload: Query) -> dict:
    text = (payload.query or "").strip()
    if not text:
        return {"answered": False, "mode": "empty", "answer": "Please enter a question.",
                "reason": "empty query", "cards": [], "citations": []}
    log.info("query", extra={"event": "query", "query": text})
    return answer_query(_STATE["index"], text).model_dump()
