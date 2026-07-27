"""
Evaluate the firm-type validation layer against the hand-labelled gold set.

Enriches + classifies each labelled firm exactly as the pipeline does, then
reports accuracy / precision / recall / FP-rate / FN-rate / confusion + the
specific false positives and false negatives. Writes machine-readable evidence.

    python scripts/eval_goldset.py
"""

from __future__ import annotations

import json
from pathlib import Path

from fointel.assemble import enrich_candidate
from fointel.discovery.base import Candidate
from fointel.enrichment.iapd import IapdEnricher
from fointel.enrichment.sec import SecEnricher
from fointel.enrichment.thirteenf import ThirteenFEnricher
from fointel.enrichment.website import WebsiteEnricher
from fointel.schema import SourceClass
from fointel.store import get_repository
from fointel.text import norm_name
from fointel.validation.goldset import Prediction, evaluate, load_goldset


def main() -> None:
    labels = load_goldset("goldset/firm_type_goldset.jsonl")
    pool = {norm_name(c.name): c for c in get_repository().all_candidates()}
    sec, web, iapd, f13 = SecEnricher(), WebsiteEnricher(), IapdEnricher(), ThirteenFEnricher()

    predictions = []
    for lab in labels:
        cand = pool.get(norm_name(lab.firm_name)) or Candidate(
            name=lab.firm_name, source_class=SourceClass.OTHER)
        e = enrich_candidate(cand, sec, web, iapd, f13)
        predictions.append(Prediction(firm_name=lab.firm_name,
                                      qualifies=e.classification.qualifies,
                                      fo_type=e.classification.fo_type.value))

    metrics = evaluate(labels, predictions)
    out = Path("docs/evidence/firmtype-goldset-eval.json")
    out.write_text(metrics.model_dump_json(indent=2), encoding="utf-8")

    print(json.dumps(metrics.model_dump(), indent=2, ensure_ascii=False))
    print(f"\nHeadline (domain-critical): precision={metrics.precision} "
          f"(FP rate={metrics.false_positive_rate}); recall={metrics.recall} "
          f"(FN rate={metrics.false_negative_rate}); type_accuracy={metrics.type_accuracy}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
