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

import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..observability import get_logger
from ..rag.answer import answer_query
from ..rag.index import RetrievalIndex
from ..rag.load import load_records_from_csv
from ..rag.roles import principal_role

log = get_logger("api")
WEB = Path(__file__).parent / "web"
_STATE: dict = {}
_GOALS: dict[str, dict] = {}   # in-memory goal-run registry: run_id -> {status, result, error}


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
        # named-person routes (only when name-matched evidence exists — see schema.py)
        "principal_email": r.principal_email,
        "principal_email_status": (r.principal_email_status.value
                                   if r.principal_email_status else None),
        "principal_linkedin": r.principal_linkedin,
        "principal_phone": r.principal_phone,
        # firm-level (not a named-person route) fallback channel
        "firm_contact_email": r.firm_contact_email,
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

    # How many independent sources actually corroborate each record. This is the
    # honest basis for any "how much can I trust this" claim the UI makes — it is
    # counted from the records being served, never asserted.
    src_counts = Counter(len(r.verification_sources) for r in records)
    evidence_strength = {
        "two_or_more_sources": sum(v for k, v in src_counts.items() if k >= 2),
        "one_source": src_counts.get(1, 0),
        "no_sources": src_counts.get(0, 0),
    }

    # Reachability, by the ONLY definition that counts for a buyer: a route to the
    # named individual. A firm's generic inbox is reported separately and is
    # explicitly NOT counted as a named-person route (see schema.py).
    def _named_route(r):
        return bool(r.principal_email or r.principal_linkedin or r.principal_phone)

    reachability = {
        "named_person_route": cov(_named_route),
        "named_person_identified_no_route": cov(
            lambda r: bool(r.principal_name) and not _named_route(r)),
        "firm_inbox_only": cov(
            lambda r: bool(r.firm_contact_email) and not _named_route(r) and not r.principal_name),
        "no_contact_information": cov(
            lambda r: not _named_route(r) and not r.principal_name and not r.firm_contact_email),
    }

    return {
        "records": n,
        "type": dict(Counter(r.fo_type.value for r in records)),
        "confidence": dict(Counter(r.record_confidence.value for r in records)),
        "evidence_strength": evidence_strength,
        "reachability": reachability,
        "coverage": {"aum": cov(lambda r: r.estimated_aum),
                     "principal": cov(lambda r: r.principal_name),
                     "principal_email": cov(lambda r: r.principal_email),
                     "principal_linkedin": cov(lambda r: r.principal_linkedin),
                     "firm_contact_email": cov(lambda r: r.firm_contact_email),
                     "website": cov(lambda r: r.website),
                     "signals": cov(lambda r: r.signals)},
        "countries": len({r.hq_country for r in records if r.hq_country}),
        "as_of": max(r.data_as_of for r in records).isoformat(),
    }


app = FastAPI(title="Family Office Intelligence", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=WEB), name="static")


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


# --------------------------------------------------------------------------- #
# Agent — multi-step goal execution. A goal run does real LLM + retrieval work
# (minutes, not milliseconds), so it runs on a background thread; the client
# polls GET /goal/{run_id} for status/result. This is the customer-facing
# agent surface: distinct from /query's single-call RAG (see src/fointel/agent).
# --------------------------------------------------------------------------- #

class Goal(BaseModel):
    goal: str


def _execute_goal(run_id: str, goal_text: str) -> None:
    from ..agent.run import run_goal, save_result
    try:
        result = run_goal(goal_text)
        save_result(result)
        _GOALS[run_id] = {"status": "done", "result": result, "error": None}
    except Exception as exc:  # noqa: BLE001 — surface to the client, never crash the server
        log.warning("goal run failed", extra={"event": "goal_error", "run_id": run_id, "error": str(exc)})
        _GOALS[run_id] = {"status": "failed", "result": None, "error": str(exc)}


@app.post("/goal")
def start_goal(payload: Goal) -> dict:
    text = (payload.goal or "").strip()
    if not text:
        return {"error": "Please enter a goal."}
    run_id = f"goal-{uuid.uuid4().hex[:10]}"
    _GOALS[run_id] = {"status": "running", "result": None, "error": None, "started_at": time.time()}
    log.info("goal started", extra={"event": "goal_start", "run_id": run_id, "goal": text})
    threading.Thread(target=_execute_goal, args=(run_id, text), daemon=True).start()
    return {"run_id": run_id, "status": "running"}


@app.get("/goal/{run_id}")
def goal_status(run_id: str) -> dict:
    entry = _GOALS.get(run_id)
    if not entry:
        return {"status": "not_found"}
    return entry
