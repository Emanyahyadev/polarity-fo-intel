"""
Evidence-based entity resolution.

Two candidates are the same firm ONLY when the evidence says so:
  1. they share a strong identifier (CIK / EIN / QID / domain), or
  2. their conservatively-normalised names are equal AND their geographies are
     compatible AND no identifier conflicts.

Anything else stays distinct. A merely similar name (high fuzzy score) is flagged
as a *possible duplicate kept distinct* for manual review — never auto-merged,
because a false merge silently deletes a real firm. Every decision (merge, kept-
distinct, new) is logged with its basis. See gate-review A4 / DecisionLog D14.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel
from rapidfuzz import fuzz

from .observability import get_logger
from .schema import Candidate
from .text import norm_name

log = get_logger("validation")

_ID_KEYS = ("cik", "ein", "qid", "domain")


class MergeDecision(BaseModel):
    incoming: str
    matched: Optional[str]
    action: str   # "new" | "merge" | "possible_duplicate_kept_distinct"
    basis: str    # "identifier:cik" | "name+geo" | "fuzzy=93" | ""
    reason: str


def _hydrate_identifiers(c: Candidate) -> None:
    for key in _ID_KEYS:
        val = c.raw.get(key) or c.hints.get(key)
        if val and key not in c.identifiers:
            c.identifiers[key] = str(val)


def _geo(c: Candidate) -> Optional[str]:
    for key in ("state", "country", "city_state", "city"):
        val = c.hints.get(key)
        if val:
            return str(val).strip().lower()
    return None


def _id_set(c: Candidate) -> set[tuple[str, str]]:
    return {(k, str(v).lower()) for k, v in c.identifiers.items() if v}


class EntityResolver:
    def __init__(self, fuzzy_threshold: int = 92):
        self.fuzzy_threshold = fuzzy_threshold

    def resolve(self, candidates: list[Candidate]) -> tuple[list[Candidate], list[MergeDecision]]:
        resolved: list[Candidate] = []
        decisions: list[MergeDecision] = []
        used_keys: set[str] = set()

        for cand in candidates:
            _hydrate_identifiers(cand)

            match, basis = self._match(cand, resolved)
            if match is not None:
                self._merge(match, cand)
                decisions.append(MergeDecision(
                    incoming=cand.name, matched=match.name, action="merge",
                    basis=basis, reason="same firm (identifier or name+geography agreement)"))
                log.info("entity merge", extra={"event": "merge", "incoming": cand.name,
                                                "kept": match.name, "basis": basis})
                continue

            dup, score = self._fuzzy_duplicate(cand, resolved)
            cand.dedup_key = self._unique_key(cand, used_keys)
            cand.discovery_sources = [cand.source_class.value]
            resolved.append(cand)

            if dup is not None:
                decisions.append(MergeDecision(
                    incoming=cand.name, matched=dup.name,
                    action="possible_duplicate_kept_distinct", basis=f"fuzzy={score}",
                    reason="similar name but no shared identifier/geo; kept distinct for review"))
                log.warning("possible duplicate kept distinct", extra={
                    "event": "possible_dup", "incoming": cand.name,
                    "similar_to": dup.name, "score": score})
            else:
                decisions.append(MergeDecision(
                    incoming=cand.name, matched=None, action="new", basis="", reason="distinct firm"))

        return resolved, decisions

    # -- matching ------------------------------------------------------- #
    def _match(self, cand: Candidate, resolved: list[Candidate]):
        ids = _id_set(cand)
        # 1) shared strong identifier
        for r in resolved:
            shared = ids & _id_set(r)
            if shared:
                return r, f"identifier:{sorted(shared)[0][0]}"
        # 2) exact normalised name + compatible geography + no id conflict
        cn, cg = norm_name(cand.name), _geo(cand)
        for r in resolved:
            if cn and cn == norm_name(r.name):
                rg = _geo(r)
                if (cg is None or rg is None or cg == rg) and not self._ids_conflict(cand, r):
                    return r, "name+geo"
        return None, ""

    @staticmethod
    def _ids_conflict(a: Candidate, b: Candidate) -> bool:
        for key in _ID_KEYS:
            va, vb = a.identifiers.get(key), b.identifiers.get(key)
            if va and vb and str(va).lower() != str(vb).lower():
                return True
        return False

    def _fuzzy_duplicate(self, cand: Candidate, resolved: list[Candidate]):
        cn = norm_name(cand.name)
        best, best_score = None, 0
        for r in resolved:
            score = int(fuzz.token_sort_ratio(cn, norm_name(r.name)))
            if score > best_score:
                best, best_score = r, score
        if best is not None and best_score >= self.fuzzy_threshold:
            return best, best_score
        return None, 0

    @staticmethod
    def _merge(keep: Candidate, incoming: Candidate) -> None:
        for key, val in incoming.identifiers.items():
            keep.identifiers.setdefault(key, val)
        src = incoming.source_class.value
        if src not in keep.discovery_sources:
            keep.discovery_sources.append(src)
        for key, val in incoming.hints.items():
            keep.hints.setdefault(key, val)

    @staticmethod
    def _unique_key(cand: Candidate, used: set[str]) -> str:
        ids = _id_set(cand)
        base = ":".join(sorted(ids)[0]) if ids else f"name:{norm_name(cand.name)}|geo:{_geo(cand) or '?'}"
        key, i = base, 2
        while key in used:  # two genuinely-distinct same-name/geo firms get distinct keys
            key = f"{base}#{i}"
            i += 1
        used.add(key)
        return key
