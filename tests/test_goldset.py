"""Gold-set metrics engine (pure)."""

from fointel.validation.goldset import GoldLabel, Prediction, evaluate


def test_confusion_and_rates():
    labels = [
        GoldLabel(firm_name="A", is_family_office=True, true_type="MFO"),   # TP (type right)
        GoldLabel(firm_name="B", is_family_office=True, true_type="SFO"),   # TP (type wrong)
        GoldLabel(firm_name="C", is_family_office=False),                   # FP (bad!)
        GoldLabel(firm_name="D", is_family_office=False),                   # TN
        GoldLabel(firm_name="E", is_family_office=True),                    # FN
    ]
    preds = [
        Prediction(firm_name="A", qualifies=True, fo_type="MFO"),
        Prediction(firm_name="B", qualifies=True, fo_type="Undetermined"),
        Prediction(firm_name="C", qualifies=True, fo_type="Undetermined"),
        Prediction(firm_name="D", qualifies=False, fo_type="Undetermined"),
        Prediction(firm_name="E", qualifies=False, fo_type="Undetermined"),
    ]
    m = evaluate(labels, preds)
    assert (m.tp, m.fp, m.tn, m.fn) == (2, 1, 1, 1)
    assert m.precision == round(2 / 3, 4)
    assert m.recall == round(2 / 3, 4)
    assert m.false_positive_rate == 0.5      # 1 FP / (1 FP + 1 TN) — the domain-critical metric
    assert m.false_negative_rate == round(1 / 3, 4)
    assert m.false_positives == ["C"] and m.false_negatives == ["E"]
    assert m.type_accuracy == 0.5            # A right, B wrong among the 2 typed TPs


def test_perfect_classifier():
    labels = [GoldLabel(firm_name="A", is_family_office=True),
              GoldLabel(firm_name="B", is_family_office=False)]
    preds = [Prediction(firm_name="A", qualifies=True, fo_type="Undetermined"),
             Prediction(firm_name="B", qualifies=False, fo_type="Undetermined")]
    m = evaluate(labels, preds)
    assert m.accuracy == 1.0 and m.precision == 1.0 and m.false_positive_rate == 0.0
