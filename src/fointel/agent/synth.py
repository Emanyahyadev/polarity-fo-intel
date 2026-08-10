"""
Final synthesis — the agent's second genuinely model-driven step: turning a
deterministic, scored, uncertainty-classified evidence bundle into plain-English
explanation and a recommended next action per candidate.

Grounded the same way the existing RAG generation is grounded (rag/answer.py):
the model may only describe what is in the evidence bundle it was given: it may
not upgrade a value's label (a firm inbox is never called a principal email, a
generic classification is never called "verified" beyond its stated confidence),
and any claim that leaks a fo_id or fact not in the bundle is rejected and the
run falls back to a deterministic templated explanation for that candidate
instead of silently shipping an unconstrained model answer.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from ..config import settings
from ..observability import get_logger
from .evidence import CandidateEvidence

log = get_logger("agent")

_SYSTEM = (
    "You are the explanation step of a family-office research agent for private-markets "
    "professionals. You will be given a GOAL and a JSON list of already-ranked, already-"
    "scored candidate family offices with their evidence. Write plain-English reasoning "
    "for the ranking.\n"
    "HARD RULES:\n"
    "1. Use ONLY the facts given in the JSON. Never invent a firm, a person, a number, or "
    "a fact not present in the JSON you were given.\n"
    "2. Never upgrade a label's strength: an item with uncertainty='thin' or 'insufficient' "
    "must be described as thin/insufficient evidence, never as confident or verified. An "
    "item with no contact_route must say no named-person contact route was found — never "
    "imply a firm inbox or a phone number reaches the principal.\n"
    "3. If uncertainty is 'insufficient' or 'stale', say so plainly and do not present a "
    "confident recommendation for that candidate.\n"
    "4. Output ONLY a JSON array, no prose outside it, one object per candidate in the same "
    "order given, each: {\"fo_id\": str, \"why\": str (2-3 sentences, cite the evidence given), "
    "\"recommended_action\": str (one sentence, tied to what contact_route/uncertainty actually allow)}."
)


def _client():
    if settings.llm_provider == "nvidia":
        from openai import OpenAI
        return OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=settings.llm_api_key)
    from groq import Groq
    return Groq(api_key=settings.llm_api_key)


def _template_explain(ev: CandidateEvidence) -> dict:
    """Deterministic fallback used when the LLM is unavailable/ungrounded — never
    blocks the run, and is exactly as conservative as the grounded LLM output must be."""
    bits = []
    if ev.sector_match:
        bits.append("sector/thesis matches the mandate")
    if ev.geography_match:
        bits.append("headquartered in the requested geography")
    bits.append(f"{ev.n_verification_sources} independent verification source(s) on file")
    why = f"{ev.uncertainty.capitalize()} evidence: " + "; ".join(bits) + f". {ev.uncertainty_reason}."
    if ev.uncertainty in ("insufficient", "stale"):
        action = "Do not prioritize yet — evidence is not strong enough to support outreach; flag for manual research."
    elif ev.contact_route:
        action = f"Reach out via the {ev.contact_route['kind'].replace('_', ' ')} on file."
    else:
        action = "No named-person contact route on file — research a decision-maker before outreach."
    return {"fo_id": ev.fo_id, "why": why, "recommended_action": action}


def explain_and_recommend(goal: str, ranked: list[CandidateEvidence], trace=None,
                          top_n: int = 15) -> list[dict]:
    subset = ranked[:top_n]
    bundle = [{
        "fo_id": e.fo_id, "name": e.name, "fo_type": e.fo_type,
        "fit_score": e.fit_score, "uncertainty": e.uncertainty,
        "uncertainty_reason": e.uncertainty_reason,
        "sector_match": e.sector_match, "geography_match": e.geography_match,
        "n_verification_sources": e.n_verification_sources,
        "record_confidence": e.record_confidence,
        "contact_route": e.contact_route,
        "principal_name": e.principal_name, "principal_title": e.principal_title,
    } for e in subset]

    if not settings.llm_api_key:
        if trace:
            trace.rejected_path("no LLM key configured; using deterministic template explanations")
        return [_template_explain(e) for e in subset]

    try:
        client = _client()
        resp = client.chat.completions.create(
            model=settings.llm_model, temperature=0.1, max_tokens=1800,
            messages=[{"role": "system", "content": _SYSTEM},
                      {"role": "user", "content": f"GOAL: {goal}\n\nCANDIDATES:\n{json.dumps(bundle)}"}])
        raw = (resp.choices[0].message.content or "").strip()
        raw = re.sub(r"<think>.*?</think>\s*", "", raw, flags=re.S).strip()
        if trace:
            trace.tool_call("llm.explain_and_recommend",
                            {"model": settings.llm_model, "n_candidates": len(subset)},
                            {"raw_len": len(raw)})
        m = re.search(r"\[.*\]", raw, re.S)
        parsed = json.loads(m.group(0)) if m else None
        if not isinstance(parsed, list):
            raise ValueError("not a JSON array")

        # Grounding check: every fo_id in the response must be one we actually sent,
        # and the response must cover every candidate we sent (else fall back per-item).
        sent_ids = {e.fo_id for e in subset}
        by_id = {}
        for item in parsed:
            if isinstance(item, dict) and item.get("fo_id") in sent_ids:
                by_id[item["fo_id"]] = item
        out = []
        rejected = 0
        for e in subset:
            item = by_id.get(e.fo_id)
            if item and item.get("why") and item.get("recommended_action"):
                out.append({"fo_id": e.fo_id, "why": item["why"],
                           "recommended_action": item["recommended_action"]})
            else:
                rejected += 1
                out.append(_template_explain(e))
        if rejected and trace:
            trace.rejected_path(f"{rejected} candidate(s) missing/ungrounded in LLM output; "
                                f"used deterministic template for those", {"rejected": rejected})
        return out
    except Exception as exc:
        log.warning("synthesis LLM call failed", extra={"event": "agent_llm_error", "error": str(exc)})
        if trace:
            trace.rejected_path("LLM synthesis call failed; used deterministic template for all candidates",
                                {"error": str(exc)[:300]})
        return [_template_explain(e) for e in subset]
