"""
Mandate understanding — the agent's first genuinely model-driven decision.

Turns a free-text customer goal into structured search criteria the
deterministic retrieval/scoring layer can execute. This is agentic (the model
decides what the criteria are and flags what is ambiguous/unanswerable from
this dataset) rather than deterministic, because open-ended natural-language
interpretation is exactly the kind of judgment a regex cannot defensibly make.
If the model call fails or returns unparseable output, we fall back to a
narrow deterministic keyword extraction and say so in the trace — we never
silently invent criteria.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from ..config import settings
from ..observability import get_logger

log = get_logger("agent")

_SYSTEM = (
    "You are the mandate-understanding step of a family-office research agent. "
    "Given a fund manager's natural-language goal, extract SEARCH CRITERIA only. "
    "Never invent facts about specific firms — you have not seen the dataset yet. "
    "Respond with ONLY a JSON object, no prose, no markdown fences, matching exactly:\n"
    "{\n"
    '  "sectors": [string],              // investing sectors/industries the mandate targets, e.g. "healthcare services"\n'
    '  "geography": [string],            // US states/countries mentioned or implied, [] if none\n'
    '  "fund_stage_or_type": string|null,// e.g. "lower-middle-market", "growth equity", null if unspecified\n'
    '  "role_sought": string|null,       // what the customer wants from the FO, e.g. "limited partner"\n'
    '  "fo_type_preference": string|null,// "Single-Family Office" | "Multi-Family Office" | null (no preference)\n'
    '  "ambiguities": [string],          // things the goal leaves unclear that could change the result\n'
    '  "unanswerable_from_dataset": [string] // parts of the mandate this kind of dataset structurally cannot verify (e.g. \'active dry powder\')\n'
    "}"
)


def _keyword_fallback(goal: str) -> dict:
    """Deterministic, narrow extraction used only if the LLM call fails."""
    g = goal.lower()
    sectors = []
    for kw in ("healthcare", "health care", "technology", "tech", "real estate",
               "energy", "consumer", "industrial", "financial services", "biotech",
               "manufacturing", "software", "infrastructure"):
        if kw in g:
            sectors.append(kw)
    states = re.findall(r"\b(texas|california|florida|new york|colorado)\b", g)
    return {
        "sectors": sectors, "geography": [s.title() for s in states],
        "fund_stage_or_type": "lower-middle-market" if "lower-middle" in g or "lower middle" in g else None,
        "role_sought": "limited partner" if "limited partner" in g or " lp" in g else None,
        "fo_type_preference": None,
        "ambiguities": ["deterministic keyword fallback used — LLM mandate parse unavailable"],
        "unanswerable_from_dataset": [],
        "_fallback": True,
    }


def _extract_json(text: str) -> Optional[dict]:
    text = re.sub(r"<think>.*?</think>\s*", "", text, flags=re.S).strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def understand_mandate(goal: str, trace=None) -> dict:
    """Returns structured criteria. Logs the raw model call as a tool_call on `trace`
    if provided, plus a rejected_path if the LLM output had to be discarded."""
    if not settings.llm_api_key:
        if trace:
            trace.rejected_path("no LLM key configured; using deterministic fallback")
        return _keyword_fallback(goal)

    try:
        if settings.llm_provider == "nvidia":
            from openai import OpenAI
            client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=settings.llm_api_key,
                            max_retries=0)
        else:
            from groq import Groq
            client = Groq(api_key=settings.llm_api_key, max_retries=0)

        resp = client.chat.completions.create(
            model=settings.llm_model, temperature=0.0, max_tokens=500, timeout=3.0,
            messages=[{"role": "system", "content": _SYSTEM},
                      {"role": "user", "content": f"GOAL: {goal}"}])
        raw = (resp.choices[0].message.content or "").strip()
        parsed = _extract_json(raw)
        if trace:
            trace.tool_call("llm.understand_mandate", {"model": settings.llm_model, "goal": goal},
                            {"raw_len": len(raw), "parsed": bool(parsed)})
        if parsed is None:
            if trace:
                trace.rejected_path("LLM mandate output not valid JSON; using deterministic fallback",
                                    {"raw_excerpt": raw[:300]})
            return _keyword_fallback(goal)
        parsed["_fallback"] = False
        return parsed
    except Exception as exc:
        log.warning("mandate LLM call failed", extra={"event": "agent_llm_error", "error": str(exc)})
        if trace:
            trace.rejected_path("LLM call raised an exception; using deterministic fallback",
                                {"error": str(exc)[:300]})
        return _keyword_fallback(goal)
