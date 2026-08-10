"""
Mandate agent orchestrator — runs one customer goal end-to-end and produces the
three deliverables the brief requires per goal: the manual-retrieval baseline
(what the existing single-call RAG returns for the same goal), the agent's
structured output, and the raw machine-readable trace.

Pipeline (mixed agentic/deterministic by design — see docs/AgentArchitecture.md):
  understand_mandate (LLM, agentic)
  -> plan_and_retrieve (deterministic: multi-source retrieval + full-scan safety net)
  -> score_and_classify per candidate (deterministic, evidence-derived)
  -> explain_and_recommend (LLM, agentic, grounded + rejection-checked)
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..compute import ComputeEngine
from ..rag.answer import answer_query
from ..rag.index import RetrievalIndex
from ..rag.load import load_records_from_store, DEFAULT_STORE
from .evidence import plan_and_retrieve
from .mandate import understand_mandate
from .synth import explain_and_recommend
from .trace import TraceRecorder

DEFAULT_TRACE_DIR = "logs/agent"
DEFAULT_OUTPUT_DIR = "reports/goals"


def run_goal(goal: str, store_path: str = DEFAULT_STORE,
            trace_dir: str = DEFAULT_TRACE_DIR, top_n: int = 10) -> dict[str, Any]:
    t0 = time.time()
    records = load_records_from_store(store_path)
    index = RetrievalIndex(records)
    dict_records = [r.model_dump(mode="json") for r in records]
    engine = ComputeEngine(dict_records)

    trace = TraceRecorder(goal=goal)

    # -- deliverable #2: the manual single-call retrieval baseline, for comparison --
    manual_t0 = time.time()
    manual = answer_query(index, goal)
    manual_elapsed = round(time.time() - manual_t0, 1)
    trace.tool_call("manual_baseline.answer_query", {"goal": goal},
                    {"answered": manual.answered, "mode": manual.mode,
                     "n_cards": len(manual.cards), "elapsed_s": manual_elapsed})

    # -- step 1: agentic mandate understanding --
    criteria = understand_mandate(goal, trace=trace)
    trace.decision("mandate_criteria", criteria)

    # -- step 2: deterministic multi-step retrieval + evidence + scoring --
    ranked = plan_and_retrieve(criteria, index, engine, trace)

    strong = [e for e in ranked if e.uncertainty == "sufficient"]
    thin = [e for e in ranked if e.uncertainty in ("thin", "stale")]
    insufficient = [e for e in ranked if e.uncertainty == "insufficient"]
    if not ranked or (not strong and not thin):
        trace.abstain("no candidate in the dataset clears even a thin-evidence bar for this mandate",
                      {"n_candidates_considered": len(ranked)})

    # -- step 3: agentic, grounded synthesis over the top N --
    explanations = explain_and_recommend(goal, ranked, trace=trace, top_n=top_n)
    by_id = {e.fo_id: e for e in ranked}
    structured = []
    for rank, exp in enumerate(explanations, start=1):
        e = by_id[exp["fo_id"]]
        structured.append({
            "rank": rank, "fo_id": e.fo_id, "family_office_name": e.name,
            "fo_type": e.fo_type,
            "fit_reasoning": exp["why"],
            "investment_focus": e.investing_sectors or (e.investment_thesis[:140] if e.investment_thesis else None),
            "recent_activity": e.signals[:2],
            "decision_maker": (f"{e.principal_name} ({e.principal_title})"
                               if e.principal_name and e.principal_title else e.principal_name),
            "contact_route": e.contact_route,
            "evidence": {"n_verification_sources": e.n_verification_sources,
                        "verification_sources": e.verification_sources,
                        "record_confidence": e.record_confidence,
                        "fo_type_evidence": e.fo_type_evidence},
            "uncertainty": e.uncertainty, "uncertainty_reason": e.uncertainty_reason,
            "fit_score": e.fit_score,
            "recommended_action": exp["recommended_action"],
        })

    trace.final({"n_ranked": len(structured),
                "counts_by_uncertainty": {"sufficient": len(strong), "thin_or_stale": len(thin),
                                          "insufficient": len(insufficient)}})
    trace_path = trace.save(trace_dir)

    elapsed = round(time.time() - t0, 1)
    result = {
        "goal": goal,
        "run_id": trace.run_id,
        "elapsed_seconds": elapsed,
        "mandate_criteria": criteria,
        "manual_retrieval_baseline": {
            "answered": manual.answered, "mode": manual.mode, "answer": manual.answer,
            "n_cards": len(manual.cards), "elapsed_seconds": manual_elapsed,
        },
        "structured_output": structured,
        "counts": {"considered": len(ranked), "sufficient_evidence": len(strong),
                  "thin_or_stale_evidence": len(thin), "insufficient_evidence": len(insufficient)},
        "trace_path": str(trace_path),
    }
    return result


def save_result(result: dict, out_dir: str = DEFAULT_OUTPUT_DIR) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{result['run_id']}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


if __name__ == "__main__":
    import sys
    goal_text = sys.argv[1] if len(sys.argv) > 1 else "Find the best family offices for my investment mandate."
    res = run_goal(goal_text)
    p = save_result(res)
    print(f"saved structured output -> {p}")
    print(f"saved trace -> {res['trace_path']}")
    print(f"elapsed {res['elapsed_seconds']}s, {res['counts']}")
