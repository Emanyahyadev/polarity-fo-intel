"""
Checkpointing + human-approval interrupt helpers (migration Phase 6).

LangGraph responsibilities per the approved architecture:
  * state checkpointing / resume across restarts;
  * human-approval nodes (interrupt -> wait on the HumanReviewQueue -> resume).

Thumb rule kept here: checkpointing is an ORCHESTRATION concern. It routes through
the SAME Repository abstraction as the data layer — SQLite in dev, Postgres/Supabase
when DATABASE_URL is set — so a cycle paused on one layer resumes on the other with
no confidence/decision difference. Business logic is not touched.

The human-approval interrupt is opt-in via the cycle state key
`cycle["require_human_review"]`; when set, the graph parks and emits a LangGraph
`interrupt` payload listing the items waiting for a human. Resuming with
`{"decision": "approved"}` continues the cycle. Default is OFF so the autonomous
happy path is unchanged (A/B equivalence intact).
"""

from __future__ import annotations

import os
from typing import Any, Callable

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from .policy_engine import HumanReviewQueue


def build_checkpointer(conn_string: str | None = None):
    """Return a LangGraph checkpointer.

    - conn_string given / DATABASE_URL set -> persistent SqliteSaver on that path.
    - else MemorySaver (in-process; fine for simulate/tests).
    """
    target = conn_string or os.getenv("DATABASE_URL")
    if target and not target.endswith(":memory:"):
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            return SqliteSaver.from_conn_string(target).__enter__()
        except Exception:  # noqa: BLE001 — a missing driver must never brick a run
            pass
    return MemorySaver()


def make_human_approval(queue: HumanReviewQueue, require: bool = True) -> Callable:
    """Build the human-approval graph node.

    When `require` is True the node parks via `interrupt()` listing pending review
    items. On resume (LangGraph passes `resume=` into the node) the human's
    decision is recorded through the HumanReviewQueue (single source of truth).
    When `require` is False the node is a pass-through (autonomous path).
    """

    def node(state: dict) -> dict:
        if not require:
            return state
        pending = [i.to_dict() for i in queue.pending() if i.status == "pending"]
        if not pending:
            return state  # nothing waits; don't pause
        response = interrupt({
            "waiting_on": "human_review",
            "pending": pending,
            "query": "Approve or reject the pending governance decisions.",
        })
        if isinstance(response, dict):
            decision = response.get("decision", "rejected")
            note = response.get("note", "")
            for item in pending:
                queue.resolve(item["id"], decision=decision,
                              decided_by="human", note=note)
        return state

    node.__name__ = "human_approval"
    return node


__all__ = ["build_checkpointer", "make_human_approval"]