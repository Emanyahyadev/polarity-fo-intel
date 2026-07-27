"""
Gold-set evaluation for the firm-type validation layer.

How We Work judges a validation layer by *measured* evidence against a hand-
labelled gold set — accuracy, precision, recall, false-positive & false-negative
rates, a confusion matrix. In THIS domain the critical error is a false POSITIVE
(shipping a non-family-office as a family office — "the most serious error"), so
precision / FP-rate is the headline; FN (a real FO we missed) is reported too.

The metrics engine here is pure and testable; `scripts/eval_goldset.py` produces
the predictions by enriching + classifying each labelled firm.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class GoldLabel(BaseModel):
    firm_name: str
    is_family_office: bool            # ground truth: is it really a family office?
    true_type: Optional[str] = None   # "SFO" / "MFO" / "Undetermined" (if a family office)
    note: str = ""                    # why (the human judgment basis)


class Prediction(BaseModel):
    firm_name: str
    qualifies: bool
    fo_type: str


class GoldsetMetrics(BaseModel):
    n: int
    tp: int
    fp: int
    tn: int
    fn: int
    accuracy: float
    precision: float          # TP/(TP+FP) — of firms we shipped as FOs, how many really are
    recall: float             # TP/(TP+FN) — of real FOs, how many we caught
    false_positive_rate: float  # FP/(FP+TN) — the domain-critical error
    false_negative_rate: float  # FN/(FN+TP)
    type_accuracy: Optional[float] = None  # among correctly-qualified FOs, SFO/MFO/Undet correctness
    false_positives: list[str] = []        # non-FOs we wrongly qualified (must be empty ideally)
    false_negatives: list[str] = []        # real FOs we rejected


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def evaluate(labels: list[GoldLabel], predictions: list[Prediction]) -> GoldsetMetrics:
    pred_by_name = {p.firm_name: p for p in predictions}
    tp = fp = tn = fn = 0
    type_correct = type_total = 0
    false_pos: list[str] = []
    false_neg: list[str] = []

    for label in labels:
        pred = pred_by_name.get(label.firm_name)
        if pred is None:
            continue
        if label.is_family_office and pred.qualifies:
            tp += 1
            if label.true_type:
                type_total += 1
                type_correct += int(pred.fo_type == label.true_type)
        elif not label.is_family_office and pred.qualifies:
            fp += 1
            false_pos.append(label.firm_name)
        elif not label.is_family_office and not pred.qualifies:
            tn += 1
        else:  # is_family_office and not qualifies
            fn += 1
            false_neg.append(label.firm_name)

    n = tp + fp + tn + fn
    return GoldsetMetrics(
        n=n, tp=tp, fp=fp, tn=tn, fn=fn,
        accuracy=_rate(tp + tn, n),
        precision=_rate(tp, tp + fp),
        recall=_rate(tp, tp + fn),
        false_positive_rate=_rate(fp, fp + tn),
        false_negative_rate=_rate(fn, fn + tp),
        type_accuracy=_rate(type_correct, type_total) if type_total else None,
        false_positives=false_pos, false_negatives=false_neg,
    )


def load_goldset(path: str) -> list[GoldLabel]:
    labels = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            labels.append(GoldLabel.model_validate_json(line))
    return labels
