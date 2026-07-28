"""
Grounding / abstention control — enforced in CODE, not prompt.

The assessment is explicit: "Prompt instructions alone are not enough." This
control does three things independent of any model:

1. Abstain: if the best retrieval similarity is below a threshold (or nothing
   matched a hard filter), the system declines rather than guessing.
2. Bound claims: a generated answer may only name family offices present in the
   retrieved set; any other named firm is treated as a hallucination.
3. Cite: every answer carries the fo_ids it is grounded in.

`verify_answer` returns the list of ungrounded firm mentions; a non-empty list
means the generation must be rejected or replaced by the extractive answer.
"""

from __future__ import annotations

import re

from ..text import norm_name
from .retrieve import Retrieved

# Proper-noun-ish spans that look like firm names (to catch invented firms).
_CANDIDATE_FIRM = re.compile(
    r"\b([A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){0,4}"
    r"\s+(?:Family Office|Family Offices|Capital|Advisors|Partners|Management|Group|LLC|LP))\b")


_FO_WORDS = re.compile(r"\b(family|offices?|llc|ltd|lp|inc|the|and)\b", re.I)

# Generic tokens that must NOT count as grounding evidence in verify_answer — every
# family-office name shares them, so matching on them lets invented firms through.
_GENERIC_TOKENS = {"family", "office", "offices", "capital", "partners", "partner",
                   "management", "advisors", "advisor", "advisory", "group", "llc", "lp",
                   "inc", "ltd", "the", "and", "of", "co", "holdings", "ventures",
                   "associates", "wealth", "investments", "investment",
                   # type/concept vocabulary: answers legitimately explain "Single-Family
                   # Office" / "Multi-Family Office" as CONCEPTS in Title Case — these are
                   # domain terms, not firm names, and must not be flagged as hallucinated
                   "single", "multi", "type", "types",
                   # common financial-prose vocabulary that Title-Case answers produce
                   # ("Regulatory Assets Under Management", "Portfolio Risk Services") —
                   # none of these is the distinguishing token of any delivered firm name
                   "assets", "under", "regulatory", "services", "service", "portfolio",
                   "risk", "private", "global", "financial", "solutions", "strategies",
                   "strategy", "planning", "legacy", "enterprise", "intergenerational",
                   # family-office CATEGORY adjectives ("Outsourced/Virtual/Embedded
                   # Family Office") — concept taxonomy, not firm names; an invented
                   # firm still needs a proper-noun token and is still flagged
                   "outsourced", "virtual", "embedded", "commercial", "traditional",
                   "hybrid", "dedicated", "boutique", "independent", "professional",
                   "direct", "unified", "integrated", "modern", "typical", "classic",
                   "common", "structured", "form", "forms"}


def _name_core(s: str) -> str:
    """Distinctive core of a name/query — drops common family-office words + punctuation, so
    'Pathstone' matches 'PATHSTONE FAMILY OFFICE, LLC' but bare 'family' matches nothing."""
    return re.sub(r"[^a-z0-9]", "", _FO_WORDS.sub("", (s or "").lower()))


# SECURITY-ONLY gate (product direction: every domain-relevant question — definitional,
# educational, how-to, advice-shaped — is ANSWERED with an explanatory response; the LLM
# explains family-office concepts as general context while every firm-specific fact
# stays record-bound, and off-domain queries are declined by the similarity threshold).
# What is never answered: attempts to override the assistant's instructions — those are
# not questions at all. Patterns are precise so legitimate finance phrasing survives
# ("firms that act as fiduciaries" is NOT matched; "act as my financial adviser" is).
_OFF_TASK = re.compile(
    r"\b(ignore|disregard|forget) (your|all|any|previous|prior|these) (instructions|rules|guidelines|prompts?)\b"
    r"|\bact as (if|though|my|our)\b|\bpose as\b|\bpretend (to be|you are)\b"
    r"|\b(system|your) prompt\b|\bjailbreak\b",
    re.IGNORECASE)


class Grounding:
    def __init__(self, min_score: float = 0.68):
        self.min_score = min_score

    def assess(self, retrieved: list[Retrieved], query: str = "",
               authoritative: bool = False) -> tuple[bool, str]:
        """Answerable if the best semantic match clears the threshold, OR the query names a
        retrieved firm (a firm-name lookup: BM25 caught it even if the bare name's cosine is
        borderline), OR an authoritative hard metadata filter matched (an in-domain query that
        constrained by state/country/type/AUM — the filter match is definitive, so a low bare
        cosine must not veto it). Otherwise abstain."""
        if not retrieved:
            return False, "no records matched the query"
        top = max(r.vector_score for r in retrieved)
        # firm mentioned in the query (either direction: bare-name lookup, or a longer
        # question containing a verified firm's distinctive name) → an in-scope record
        # lookup, which also bypasses the off-task gate below
        qcore = _name_core(query)
        named = False
        for r in retrieved:
            rcore = _name_core(r.record.name)
            if rcore and ((len(qcore) >= 4 and qcore in rcore)
                          or (len(rcore) >= 5 and rcore in qcore)):
                named = True
                break
        # security gate: instruction-override attempts are declined in code regardless of
        # similarity — a query is data, never instructions
        if not named and _OFF_TASK.search(query):
            return False, ("out-of-scope request (instruction override) — queries are treated "
                           "as questions about the records, never as instructions")
        if named:
            return True, f"firm-name match (best similarity {top:.2f})"
        if authoritative:
            return True, "matched an authoritative metadata filter (state/country/type/AUM)"
        if top >= self.min_score:
            return True, f"top similarity {top:.2f}"
        return False, f"best match similarity {top:.2f} is below the {self.min_score} threshold"

    def verify_answer(self, answer_text: str, retrieved: list[Retrieved]) -> list[str]:
        """Return firm names asserted in the answer that are NOT in the retrieved set.

        The allowlist is the CONTEXT the model was given: a mention is grounded if its
        distinctive tokens appear in a retrieved firm's name OR anywhere in its record text
        (e.g. 'LEGO Group' inside KIRKBI's evidence is a record fact, not an invention).
        Generic family-office/finance words never count as grounding, so an invented name
        like 'Zephyr Quantum Family Office' is flagged, and an all-generic phrase is not
        treated as a firm at all (ordinary 'Wealth Management' prose is not rejected). Known
        residual gap: an invented name that borrows ONE distinctive token from the retrieved
        context (e.g. 'Pathstone Ventures') is still treated as a partial reference; the LLM
        prompt + abstention threshold are the backstops there."""
        from .index import record_text
        allowed = {norm_name(r.record.name) for r in retrieved}
        allowed_tokens = {t for name in allowed for t in name.split() if t not in _GENERIC_TOKENS}
        for r in retrieved:   # entities inside the record text are record-grounded too
            allowed_tokens.update(t for t in norm_name(record_text(r.record)).split()
                                  if t not in _GENERIC_TOKENS)
        ungrounded = []
        for match in _CANDIDATE_FIRM.finditer(answer_text or ""):
            mentioned = norm_name(match.group(1))
            if not mentioned:
                continue
            if mentioned in allowed:
                continue
            distinctive = [t for t in mentioned.split() if t not in _GENERIC_TOKENS]
            if not distinctive:
                continue  # an all-generic phrase ("Wealth Management", "Capital Partners") is
                # not a distinctive firm name — flagging it would reject valid grounded answers
            if any(t in allowed_tokens for t in distinctive):
                continue  # shares a DISTINCTIVE token with a retrieved firm
            ungrounded.append(match.group(1))
        return sorted(set(ungrounded))
