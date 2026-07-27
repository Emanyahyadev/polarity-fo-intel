# Validation

How the system decides what is trustworthy enough to ship, and how well that decision works. Following **How We Work**, validation is a distinct build type from the production pipeline and is judged on *measured* evidence (a gold set, false-positive / false-negative rates), not throughput.

## 1. Two build types, two evidence standards

- **Production systems** (discovery, enrichment, retrieval, serving) — judged operationally: do they run end-to-end without silent failure, and how do they behave under load/edge cases.
- **The validation layer** (firm-type classification, email verification, the release gate) — judged by measurement: accuracy, precision, recall, FP rate, **FN rate**, confusion matrix, against a hand-labelled gold set. A false negative (a bad value we labelled good) is the deadly error because it ships downstream with the system's confidence.

## 2. The release gate — single publication authority

`fointel.validation.gates.ReleaseGate` is the only path to a released record. A record ships only if **all** mandatory gates pass; every withhold is logged with reasons to the `release` channel. This is where "findings govern releases" is enforced in code.

| Gate | Guarantees |
|---|---|
| G1 `family_office_evidenced` | Rule 2 — affirmative FO evidence exists |
| G2 `classification_evidence` | a typed SFO/MFO carries classification evidence |
| G3 `discovery_documented` | how the firm was found is recorded |
| G4 `verification_documented` | ≥1 authoritative (non-discovery-only) verification source |
| G5 `verification_authoritative` | Wikipedia/Wikidata (discovery-only) can never verify |
| G6 `no_contradictions` | discovery ≠ verification (independence) unless justified |
| G7 `mandatory_fields_complete` | name + geography + ≥1 actionable/entity-intelligence path |
| G8 `provenance_complete` | Rule 1 — every populated high-value cell has a basis |
| G9 `no_rejected_values_shipped` | **a value in the audit trail can never appear in any delivered field** |

The core invariant (G9) is protected by an automated test in both directions: the leak-caught case (fails) and the value-removed case (passes).

## 3. Provenance enforcement (Rule 1)

Enforced in code, not documentation:
- **Construction-time invariant** (`@model_validator`): a field can never be both populated and marked `could_not_verify`.
- **`provenance_violations()`**: every populated high-value field must carry provenance, and a classified FO must carry classification evidence. The gate (G8) blocks release on any violation.

## 4. Gold-set evaluation (Wave 2)

A **25–30 record** hand-reviewed gold set for firm-type classification. `validation/goldset.py` will report **accuracy, precision, recall, FP rate, FN rate, and a confusion matrix**, plus concrete failure examples, root-cause analysis, and improvement notes — reading like a production ML evaluation. A separate small gold set of known-good/known-bad addresses will measure the email checker's own FP/FN. Metrics land here (and machine-readable JSON in `docs/evidence/02-firmtype-goldset-eval.json`) as Wave 2 ships.

## 5. Email verification (honest by design)

We do **not** perform SMTP RCPT probing: from free/cloud IPs it is unreliable (greylisting → false undeliverables; catch-all domains → false deliverables) and treated as abusive (blacklisting risk). Instead, verification uses syntax + MX/domain liveness + role/pattern heuristics, and where genuine deliverability cannot be established on free tooling, the value is left blank and marked `could_not_verify`. A guessed value dressed as "verified" is never shipped; an honest blank is. (Gate-review A8.)

## 6. Two layers tested (Wave 3)

The dataset and the deployed answer are separate failure surfaces. Wave 3 adds a RAG evaluation harness measuring answer faithfulness and abstention on unanswerable queries, with real logged live queries — because testing the records does not test the answers.
