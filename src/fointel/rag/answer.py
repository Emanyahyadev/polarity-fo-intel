"""
Answer generation — grounded, with abstention.

Pipeline: parse filters -> hybrid retrieve -> grounding.assess (abstain if weak)
-> generate. Generation is an LLM (Groq, free tier) when a key is configured,
otherwise a deterministic extractive answer built only from verified fields. In
either case the grounding control bounds the output: an LLM answer that names a
firm not in the retrieved set is rejected and replaced by the extractive answer.
Every answer carries citations (fo_ids) and never invents data.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from ..config import settings
from ..observability import get_logger
from ..schema import SourceClass
from .ground import Grounding

_VERIFY_LABEL = {
    SourceClass.SEC_EDGAR.value: "SEC 13F/SC filing",
    SourceClass.SEC_IAPD.value: "SEC Form ADV registration",
    SourceClass.FIRM_SITE.value: "firm website",
    SourceClass.IRS_990PF.value: "IRS 990-PF",
    SourceClass.NEWS.value: "news",
    SourceClass.DIRECTORY.value: "curated directory",
}
from .index import RetrievalIndex, parse_filters, record_text
from .retrieve import Retrieved, retrieve

log = get_logger("retrieval")

ABSTAIN_MESSAGE = (
    "I don't have enough verified information to answer that from this dataset. "
    "This service only answers from a validated set of family-office records; "
    "try naming a family-office type (single- or multi-family), a US state, an "
    "investing focus, or a firm name.")


class AnswerResult(BaseModel):
    query: str
    answered: bool
    answer: str
    reason: str
    mode: str                       # "llm" | "extractive" | "extractive-fallback" | "abstain"
    citations: list[str] = []
    cards: list[dict] = []


def _card(r: Retrieved) -> dict:
    rec = r.record
    return {
        "fo_id": rec.fo_id, "name": rec.name, "type": rec.fo_type.value,
        "location": ", ".join(x for x in [rec.hq_city, rec.hq_state, rec.hq_country] if x),
        "phone": rec.hq_phone, "website": rec.website, "linkedin": rec.corporate_linkedin,
        "description": rec.description, "aum": rec.estimated_aum,
        "confidence": rec.record_confidence.value, "classification_evidence": rec.fo_type_evidence,
        "verification": sorted({_VERIFY_LABEL.get(s.source_class.value, s.source_class.value)
                                for s in rec.verification_sources}),
        "match": round(r.vector_score, 3),
    }


def extractive_answer(retrieved: list[Retrieved]) -> str:
    lines = [f"Found {len(retrieved)} matching family office"
             f"{'s' if len(retrieved) != 1 else ''} in the verified dataset:"]
    for r in retrieved:
        rec = r.record
        bits = [f"{rec.name} — {rec.fo_type.value}"]
        loc = ", ".join(x for x in [rec.hq_city, rec.hq_state, rec.hq_country] if x)
        if loc:
            bits.append(loc)
        if rec.hq_phone:
            bits.append(f"phone {rec.hq_phone}")
        if rec.website:
            bits.append(rec.website)
        bits.append(f"[{rec.record_confidence.value} confidence]")
        lines.append("• " + " · ".join(bits))
    return "\n".join(lines)


def _llm_answer(query: str, retrieved: list[Retrieved]) -> str:
    from groq import Groq

    context = "\n".join(f"[{r.record.fo_id}] {record_text(r.record)}" for r in retrieved)
    system = ("You are a family-office intelligence assistant for institutional investors. "
              "Answer ONLY from the records provided. Cite firm names exactly as written. "
              "If the records do not answer the question, say so plainly. "
              "Never invent firms, contacts, or facts.")
    user = f"Records:\n{context}\n\nQuestion: {query}\n\nAnswer:"
    client = Groq(api_key=settings.llm_api_key)
    resp = client.chat.completions.create(
        model=settings.llm_model, temperature=0, max_tokens=500,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    return (resp.choices[0].message.content or "").strip()


def answer_query(index: RetrievalIndex, query: str, grounding: Optional[Grounding] = None,
                 top_k: Optional[int] = None) -> AnswerResult:
    grounding = grounding or Grounding(settings.min_retrieval_score)
    top_k = top_k or settings.retrieval_top_k

    filters = parse_filters(query)
    retrieved = retrieve(index, query, top_k=top_k, filters=filters)
    answerable, reason = grounding.assess(retrieved)
    if not answerable:
        log.info("abstain", extra={"event": "abstain", "query": query, "reason": reason})
        return AnswerResult(query=query, answered=False, answer=ABSTAIN_MESSAGE,
                            reason=reason, mode="abstain")

    # Trim semantic padding. With no hard metadata filter, keep only results at/above the
    # relevance threshold, so a specific query (e.g. a firm name) returns the genuinely
    # relevant record(s) instead of the padded top-k. Metadata-filtered results already
    # satisfy a hard constraint (state/type), so they are shown as-is.
    if not filters:
        strong = [r for r in retrieved if r.vector_score >= grounding.min_score]
        if strong:
            retrieved = strong

    cards = [_card(r) for r in retrieved]
    citations = [r.record.fo_id for r in retrieved]

    if settings.llm_api_key:
        try:
            text = _llm_answer(query, retrieved)
            ungrounded = grounding.verify_answer(text, retrieved)
            if ungrounded:
                log.warning("ungrounded claims -> extractive fallback", extra={
                    "event": "grounding_reject", "query": query, "ungrounded": ungrounded})
                return AnswerResult(query=query, answered=True, answer=extractive_answer(retrieved),
                                    reason=reason, mode="extractive-fallback",
                                    citations=citations, cards=cards)
            return AnswerResult(query=query, answered=True, answer=text, reason=reason,
                                mode="llm", citations=citations, cards=cards)
        except Exception as exc:
            log.warning("llm failed -> extractive", extra={"event": "llm_error",
                        "query": query, "error": str(exc)})

    return AnswerResult(query=query, answered=True, answer=extractive_answer(retrieved),
                        reason=reason, mode="extractive", citations=citations, cards=cards)
