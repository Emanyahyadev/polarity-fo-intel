"""
RAG evaluation — grounding & abstention on labelled queries.

Tests BOTH layers the assessment cares about: (1) that answerable queries return
grounded answers citing real records, and (2) that unanswerable / off-topic
queries are DECLINED rather than answered with false confidence. Writes a
machine-readable result + a human-readable transcript to docs/evidence/.

    python scripts/eval_rag.py
"""

from __future__ import annotations

import json
from pathlib import Path

from fointel.config import settings
from fointel.rag.answer import answer_query
from fointel.rag.index import RetrievalIndex
from fointel.rag.load import load_records_from_csv

# (query, should_answer)
QUERIES = [
    ("single-family offices in Texas", True),
    ("multi-family offices", True),
    ("family offices in Florida", True),
    ("family offices in New York", True),
    ("single-family offices in Belgium", True),     # international: Korys (authoritative country+type filter)
    ("family offices in France", True),             # international: Financière Agache
    ("family offices in Denmark", True),            # international: KIRKBI
    ("Pathstone", True),
    ("family offices focused on private equity", True),
    ("what is the best pizza in Chicago", False),
    ("best pizza office in Chicago", False),        # domain-word probe: "office" must not defeat abstention
    ("best pizza in Texas", False),                 # a state name must NOT force an off-topic answer
    ("cheap office space in Manhattan", False),     # domain-word probe
    ("how do I bake sourdough bread", False),
    ("tomorrow's weather forecast", False),
    ("predict the price of bitcoin next year", False),
    ("family offices headquartered on the moon", False),
]


def main() -> None:
    records = load_records_from_csv()
    index = RetrievalIndex(records)

    results = []
    correct = 0
    transcript = ["# RAG grounding & abstention evaluation\n",
                  f"Dataset: {len(records)} validated records. "
                  f"Abstention threshold: min cosine {settings.min_retrieval_score}.\n"]
    for query, should_answer in QUERIES:
        r = answer_query(index, query)
        ok = (r.answered == should_answer)
        correct += ok
        results.append({"query": query, "expected_answer": should_answer,
                        "answered": r.answered, "mode": r.mode, "reason": r.reason,
                        "citations": r.citations, "correct": ok})
        transcript.append(f"## Q: {query}\n"
                          f"- expected: {'answer' if should_answer else 'ABSTAIN'} · "
                          f"got: {'answer' if r.answered else 'ABSTAIN'} · "
                          f"{'✓' if ok else '✗ MISMATCH'} · mode={r.mode} · {r.reason}\n"
                          f"- {r.answer.splitlines()[0] if r.answer else ''}\n")

    accuracy = round(correct / len(QUERIES), 3)
    ev = Path("docs/evidence")
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "rag-abstention-eval.json").write_text(
        json.dumps({"n": len(QUERIES), "correct": correct, "accuracy": accuracy,
                    "results": results}, indent=2), encoding="utf-8")
    (ev / "rag-abstention-eval.md").write_text("\n".join(transcript), encoding="utf-8")

    print(f"RAG abstention/grounding accuracy: {correct}/{len(QUERIES)} = {accuracy}")
    for res in results:
        flag = "OK " if res["correct"] else "!! "
        print(f"  {flag}[{'answer ' if res['answered'] else 'abstain'}] {res['query']}")


if __name__ == "__main__":
    main()
