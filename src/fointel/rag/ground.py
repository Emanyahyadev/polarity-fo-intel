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


def _name_core(s: str) -> str:
    """Distinctive core of a name/query — drops common family-office words + punctuation, so
    'Pathstone' matches 'PATHSTONE FAMILY OFFICE, LLC' but bare 'family' matches nothing."""
    return re.sub(r"[^a-z0-9]", "", _FO_WORDS.sub("", (s or "").lower()))


class Grounding:
    def __init__(self, min_score: float = 0.68):
        self.min_score = min_score

    def assess(self, retrieved: list[Retrieved], query: str = "") -> tuple[bool, str]:
        """Answerable if the best semantic match clears the threshold, OR the query names a
        retrieved firm (a firm-name lookup: BM25 caught it even if the bare name's cosine is
        borderline). Otherwise abstain."""
        if not retrieved:
            return False, "no records matched the query"
        top = max(r.vector_score for r in retrieved)
        if top >= self.min_score:
            return True, f"top similarity {top:.2f}"
        qcore = _name_core(query)
        if len(qcore) >= 4 and any(qcore in _name_core(r.record.name) for r in retrieved):
            return True, f"firm-name match (best similarity {top:.2f})"
        return False, f"best match similarity {top:.2f} is below the {self.min_score} threshold"

    def verify_answer(self, answer_text: str, retrieved: list[Retrieved]) -> list[str]:
        """Return firm names asserted in the answer that are NOT in the retrieved set."""
        allowed = {norm_name(r.record.name) for r in retrieved}
        # allow any single-token subset match too (retrieved names are the source of truth)
        allowed_tokens = {t for name in allowed for t in name.split()}
        ungrounded = []
        for match in _CANDIDATE_FIRM.finditer(answer_text or ""):
            mentioned = norm_name(match.group(1))
            if not mentioned:
                continue
            if mentioned in allowed:
                continue
            if any(tok in allowed_tokens for tok in mentioned.split()):
                continue  # a partial/aliased reference to a retrieved firm
            ungrounded.append(match.group(1))
        return sorted(set(ungrounded))
