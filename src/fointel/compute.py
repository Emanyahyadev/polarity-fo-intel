"""
Deterministic Computation Service (Corrections 1, 4, 5 — enforced, not prose).

Phase 1 Step 3 (Eman's plan): ALL business calculations move OUT of the LLM and
into SQL/Python over the COMPLETE release-authorized dataset. The RAG/agent may
only call this service for counts, filters, totals, distributions, comparisons,
reachability, coverage, freshness, and whole-dataset claims.

Contract with the rest of the system:
  * Retrieval answers questions about IDENTIFIED records.
  * Every aggregate answer below states its denominator and coverage explicitly.
  * Capital measures are never mixed: 13F securities value, regulatory AUM, and
    estimated wealth are separate typed measures with separate as-of dates, and a
    total only ever sums one measure type.
  * Every displayed total carries a recompute trace: the inputs it was computed
    from, so a reviewer can independently re-add them and get the same number.
  * Compound questions decompose into their supported parts; unsupported parts
    are returned as explicitly-marked gaps, never silently dropped and never
    refused as a block.

This module is deterministic and dependency-light (pandas is optional for input).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field, asdict
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

# --------------------------------------------------------------------------- #
# Capital measure typing (Correction 5)
# --------------------------------------------------------------------------- #

class MeasureType(str, Enum):
    THIRTEEN_F_SECURITIES = "13F_securities_value"
    REGULATORY_AUM = "regulatory_aum"
    ESTIMATED_WEALTH = "estimated_wealth"
    UNKNOWN = "unknown"


# Distinct as-of dates, sources, and types are carried WITH each measure. This is
# what makes mixing a schema error, not a wording problem.
@dataclass(frozen=True)
class CapitalMeasure:
    amount: float                      # numeric value, USD
    measure_type: MeasureType
    as_of: Optional[str] = None        # ISO date (or year) the measure refers to
    source: Optional[str] = None
    fo_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "fo_id": self.fo_id, "amount": self.amount,
            "measure_type": self.measure_type.value,
            "as_of": self.as_of, "source": self.source,
        }


# --------------------------------------------------------------------------- #
# Output containers — every aggregate is scoped, typed, and recomputable
# --------------------------------------------------------------------------- #

@dataclass
class Scope:
    """What population an aggregate actually covers. No full-dataset label without
    stating how many records were searched, qualified, and included."""
    total_records: int                 # records in the complete release dataset
    searched: int                      # records examined for this question
    qualified: int                     # records meeting the filter/condition
    carried_measure: int               # records carrying the required measure (None -> omitted)
    included_in_calc: int              # records actually included in the computation
    note: Optional[str] = None


@dataclass
class AggregateAnswer:
    """A deterministic, scoped, recomputable aggregate."""
    kind: str                          # "count" | "total" | "distribution" | "comparison" | "coverage"
    value: Any
    measure_type: Optional[str] = None
    scope: Optional[Scope] = None
    recompute: dict = field(default_factory=dict)   # exact inputs -> independent re-add possible
    gaps: list[dict] = field(default_factory=list)  # unsupported/decomposed-missing parts

    def to_dict(self) -> dict:
        d = asdict(self)
        if d.get("scope") is not None:
            d["scope"] = d["scope"].__dict__ if isinstance(d["scope"], Scope) else dict(d["scope"])
        return d


class ComputeError(Exception):
    pass


class MixedMeasureError(ComputeError):
    """Raised when a total would mix incompatible measure types."""


# --------------------------------------------------------------------------- #
# AUM string parser — turns the Stage 1 free-text AUM cells into typed measures
# --------------------------------------------------------------------------- #

_AUM_RE = re.compile(
    r"\$\s*([\d,]+(?:\.\d+)?)\s*(billion|million|thousand|[BbMmKk]|)\b", re.IGNORECASE)


def _num(v: str) -> float:
    return float(v.replace(",", ""))


def _scale(unit: str) -> float:
    u = unit.strip().lower()
    if u in ("billion", "b"):
        return 1e9
    if u in ("million", "m"):
        return 1e6
    if u in ("thousand", "k"):
        return 1e3
    return 1.0


def parse_aum(text: str) -> Optional[CapitalMeasure]:
    """Parse a Stage 1 AUM cell into a TYPED CapitalMeasure.

    Examples:
      '$228.5M in 13(f) securities as of 03-31-2026 (SEC Form 13F, 103 positions)'
        -> CapitalMeasure(228.5e6, THIRTEEN_F_SECURITIES, '2026-03-31', 'SEC Form 13F')
      '$2.48B total regulatory AUM (SEC Form ADV Item 5.F as of 2024)'
        -> CapitalMeasure(2.48e9, REGULATORY_AUM, '2024', 'SEC Form ADV Item 5.F')
    """
    if not text:
        return None
    m = _AUM_RE.search(text)
    if not m:
        return None
    amount = _num(m.group(1)) * _scale(m.group(2) or "1")
    lower = text.lower()
    if "13(f)" in lower or "13f" in lower:
        mtype = MeasureType.THIRTEEN_F_SECURITIES
        source = "SEC Form 13F"
    elif "adv" in lower or "regulatory aum" in lower:
        mtype = MeasureType.REGULATORY_AUM
        source = "SEC Form ADV"
    else:
        mtype = MeasureType.UNKNOWN
        source = None
    # extract as-of date (yyyy-mm-dd or year)
    as_of: Optional[str] = None
    dm = re.search(r"as of (\d{4})-(\d{2})-(\d{2})", text)
    if dm:
        as_of = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}"
    else:
        ym = re.search(r"as of (\d{4})", text)
        if ym:
            as_of = ym.group(1)
    return CapitalMeasure(amount=round(amount, 2), measure_type=mtype, as_of=as_of, source=source)


# --------------------------------------------------------------------------- #
# The computation engine
# --------------------------------------------------------------------------- #

class ComputeEngine:
    """Deterministic computation over the COMPLETE release-authorized dataset.

    Loads the committed release CSV once (like the serving index does) and answers
    aggregate questions by computation only. Never by retrieval sampling.
    """

    def __init__(self, records: Iterable[dict[str, Any]]):
        self.records = [r for r in records]
        # cache parsed measures per fo_id (typed + dated)
        self._measures: dict[str, list[CapitalMeasure]] = {}
        for r in self.records:
            pm = parse_aum(r.get("estimated_aum") or "")
            if pm:
                pm = CapitalMeasure(amount=pm.amount, measure_type=pm.measure_type,
                                    as_of=pm.as_of, source=pm.source, fo_id=r.get("fo_id"))
                self._measures.setdefault(r.get("fo_id"), []).append(pm)

    # -- helpers ----------------------------------------------------------- #
    @property
    def total_records(self) -> int:
        return len(self.records)

    def _match(self, r: dict, **conds) -> bool:
        for field, val in conds.items():
            if val is None:
                continue
            got = r.get(field)
            if got is None:
                if val is not None:
                    return False
                continue
            if isinstance(val, (list, tuple, set)):
                if got not in val:
                    return False
            else:
                if str(got) != str(val):
                    return False
        return True

    # -- counts ------------------------------------------------------------ #
    def count(self, **conds) -> AggregateAnswer:
        """Deterministic count over the complete dataset. `conds` are field==value
        filters (fo_type, hq_country, hq_state, record_confidence, ...)."""
        searched = self.records
        qualified = [r for r in searched if self._match(r, **conds)]
        ans = AggregateAnswer(
            kind="count",
            value=len(qualified),
            scope=Scope(
                total_records=len(self.records),
                searched=len(searched),
                qualified=len(qualified),
                carried_measure=None,
                included_in_calc=len(searched),
            ),
            recompute={"filters": {k: v for k, v in conds.items() if v is not None}},
        )
        return ans

    # -- totals (measure-type-safe, Correction 5) --------------------------- #
    def total(self, measure_type: Optional[MeasureType | str] = None, **conds) -> AggregateAnswer:
        """Sum a capital measure across records matching `conds`.

        Raises MixedMeasureError if a record carries multiple distinct measure
        types and none is requested — the service refuses to fold them together.
        """
        if isinstance(measure_type, str):
            try:
                measure_type = MeasureType(measure_type)
            except ValueError:
                raise ComputeError(f"unknown measure_type {measure_type!r}; "
                                   f"valid: {[m.value for m in MeasureType]}")
        searched = self.records
        qualified = [r for r in searched if self._match(r, **conds)]
        rows: list[tuple[dict, CapitalMeasure]] = []
        for r in qualified:
            for m in self._measures.get(r.get("fo_id"), []):
                rows.append((r, m))

        types_present = {m.measure_type for _, m in rows}
        if measure_type is None:
            if len(types_present) > 1:
                raise MixedMeasureError(
                    f"refusing to total {len(rows)} measures mixing types "
                    f"{sorted(t.value for t in types_present)}; require an explicit measure_type"
                )
            measure_type = next(iter(types_present), MeasureType.UNKNOWN)

        included = [(r, m) for r, m in rows if m.measure_type == measure_type]
        total = round(sum(m.amount for _, m in included), 2)
        items = [m.to_dict() for _, m in included]
        ans = AggregateAnswer(
            kind="total",
            value=total,
            measure_type=measure_type.value,
            scope=Scope(
                total_records=len(self.records),
                searched=len(searched),
                qualified=len(qualified),
                carried_measure=len(rows),
                included_in_calc=len(included),
            ),
            recompute={
                "measure_type": measure_type.value,
                "n_included": len(included),
                "items": items,               # exact inputs -> independent re-add
                "sum_of_items": round(sum(i["amount"] for i in items), 2),
            },
        )
        # invariant: displayed value == recompute sum of displayed items
        if abs(ans.recompute["sum_of_items"] - total) > 0.005:
            raise ComputeError("internal: total != sum of displayed items")
        return ans

    # -- distribution ------------------------------------------------------- #
    def distribution(self, field: str, **conds) -> AggregateAnswer:
        searched = self.records
        qualified = [r for r in searched if self._match(r, **conds)]
        counts: dict[str, int] = {}
        for r in qualified:
            v = r.get(field)
            key = str(v) if v not in (None, "") else "(blank)"
            counts[key] = counts.get(key, 0) + 1
        ans = AggregateAnswer(
            kind="distribution",
            value=dict(sorted(counts.items(), key=lambda kv: -kv[1])),
            scope=Scope(
                total_records=len(self.records),
                searched=len(searched),
                qualified=len(qualified),
                carried_measure=None,
                included_in_calc=len(qualified),
            ),
            recompute={"field": field, "filters": {k: v for k, v in conds.items() if v is not None}},
        )
        if sum(counts.values()) != len(qualified):
            raise ComputeError("internal: distribution rows != qualified rows")
        return ans

    # -- route / reachability coverage (Correction 7) ------------------------ #
    def route_coverage(self, route_field: str = "principal_email",
                       route_status_field: Optional[str] = None) -> AggregateAnswer:
        """Honest reachability coverage BY TYPE so a buyer sees what they get."""
        searched = self.records
        with_route = 0
        verified_route = 0
        route_rows: list[dict] = []
        for r in searched:
            val = r.get(route_field)
            has = bool(val and str(val).strip() not in ("", "NA", "could_not_verify"))
            status = ""
            if route_status_field and r.get(route_status_field):
                status = str(r.get(route_status_field))
            verified = has and (status in ("deliverable", "approved", "verified"))
            if has:
                with_route += 1
            if verified:
                verified_route += 1
            route_rows.append({"fo_id": r.get("fo_id"), "has_route": has,
                               "status": status, "verified": verified})
        ans = AggregateAnswer(
            kind="coverage",
            value={"with_route": with_route, "verified_route": verified_route},
            scope=Scope(
                total_records=len(searched),
                searched=len(searched),
                qualified=with_route,
                carried_measure=verified_route,
                included_in_calc=len(searched),
            ),
            recompute={"route_field": route_field, "rows": route_rows},
        )
        return ans

    # -- compound decomposition (Correction 4) -------------------------------- #
    def decompose(self, question: str, part_map: list[dict]) -> dict:
        """A compound question is split into supported parts. `part_map` is a list of
        {key, resolved_by, answer, gap?}. This service never silently drops a part."""
        return {
            "question": question,
            "parts": part_map,
            "decomposed": True,
            "note": "supported parts are answered; unsupported parts are explicitly marked",
        }

    # -- freshness snapshot --------------------------------------------------- #
    def freshness_snapshot(self) -> AggregateAnswer:
        """Whole-dataset freshness: data_as_of coverage and staleness of each record
        relative to 'today'. Deterministic, denominator-stated."""
        from collections import Counter
        asof = Counter(str(r.get("data_as_of")) or "(none)" for r in self.records)
        ans = AggregateAnswer(
            kind="distribution",
            value=dict(asof),
            scope=Scope(total_records=len(self.records), searched=len(self.records),
                        qualified=len(self.records), carried_measure=None,
                        included_in_calc=len(self.records)),
            recompute={"field": "data_as_of"},
        )
        return ans


# --------------------------------------------------------------------------- #
# Loader + factory
# --------------------------------------------------------------------------- #

def load_records_from_csv(csv_path: str | Path) -> list[dict[str, Any]]:
    import csv
    with open(csv_path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def build_engine(csv_path: str | Path) -> ComputeEngine:
    return ComputeEngine(load_records_from_csv(csv_path))


def _demo() -> None:
    import sys
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/final/family_offices.csv")
    eng = build_engine(p)
    print(json.dumps(eng.count(fo_type="Multi-Family Office").to_dict(), indent=2))
    print(json.dumps(eng.total(measure_type="THIRTEEN_F_SECURITIES").to_dict(), indent=2))


if __name__ == "__main__":
    _demo()