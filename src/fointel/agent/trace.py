"""
Machine-readable execution trace for the customer-facing mandate agent.

One JSONL file per run: every plan step, tool/retrieval call, intermediate
decision, candidate comparison, evidence reference, rejected path, uncertainty
check, retry, and escalation is a separate line, in the order it happened.
This is the raw trace required alongside the structured output and the
manual-retrieval baseline — never a narrated summary standing in for it.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


@dataclass
class TraceRecorder:
    goal: str
    run_id: str = field(default_factory=lambda: f"goal-{uuid.uuid4().hex[:10]}")
    events: list[dict[str, Any]] = field(default_factory=list)

    def _emit(self, kind: str, **payload: Any) -> None:
        self.events.append({"ts": _now(), "run_id": self.run_id, "kind": kind, **payload})

    def plan(self, steps: list[str]) -> None:
        self._emit("plan", steps=steps)

    def tool_call(self, name: str, args: dict, result_summary: Any) -> None:
        self._emit("tool_call", tool=name, args=args, result_summary=result_summary)

    def retrieval(self, query: str, filters: dict, hit_count: int, fo_ids: list[str]) -> None:
        self._emit("retrieval", query=query, filters=filters, hit_count=hit_count, fo_ids=fo_ids)

    def decision(self, name: str, detail: Any) -> None:
        self._emit("intermediate_decision", name=name, detail=detail)

    def comparison(self, candidates: list[dict]) -> None:
        self._emit("candidate_comparison", candidates=candidates)

    def evidence_ref(self, fo_id: str, field: str, source_class: str, note: str = "") -> None:
        self._emit("evidence_reference", fo_id=fo_id, field=field,
                    source_class=source_class, note=note)

    def rejected_path(self, reason: str, detail: Any = None) -> None:
        self._emit("rejected_path", reason=reason, detail=detail)

    def uncertainty_check(self, fo_id: str, verdict: str, reason: str) -> None:
        self._emit("uncertainty_check", fo_id=fo_id, verdict=verdict, reason=reason)

    def retry(self, what: str, attempt: int, reason: str) -> None:
        self._emit("retry", what=what, attempt=attempt, reason=reason)

    def escalation(self, reason: str, detail: Any = None) -> None:
        self._emit("escalation", reason=reason, detail=detail)

    def abstain(self, reason: str, detail: Any = None) -> None:
        self._emit("abstain", reason=reason, detail=detail)

    def final(self, answer: Any) -> None:
        self._emit("final_answer", answer=answer)

    # ------------------------------------------------------------------ #
    def save(self, out_dir: str | Path) -> Path:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.run_id}.jsonl"
        with open(path, "w", encoding="utf-8") as fh:
            for ev in self.events:
                fh.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
        return path
