"""
Presentation layer — FastAPI service for the Micro-RAG.

Separation of concerns: this layer only handles HTTP + rendering; all retrieval,
grounding, and generation live in fointel.rag. The index is built once at startup
from the committed deliverable CSV. Endpoints:

    GET  /        the customer-facing UI (non-technical)
    GET  /health  liveness + record count
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

log = get_logger("api")
WEB = Path(__file__).parent / "web"
_STATE: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    records = load_records_from_csv()
    _STATE["index"] = RetrievalIndex(records)
    _STATE["count"] = len(records)
    log.info("index ready", extra={"event": "startup", "records": len(records)})
    yield


app = FastAPI(title="Family Office Intelligence", version="1.0.0", lifespan=lifespan)


class Query(BaseModel):
    query: str


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (WEB / "index.html").read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "records": _STATE.get("count", 0)}


@app.post("/query")
def query(payload: Query) -> dict:
    text = (payload.query or "").strip()
    if not text:
        return {"answered": False, "mode": "empty", "answer": "Please enter a question.",
                "reason": "empty query", "cards": [], "citations": []}
    log.info("query", extra={"event": "query", "query": text})
    return answer_query(_STATE["index"], text).model_dump()
