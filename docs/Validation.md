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

## 4. Gold-set evaluation (measured)

A **25-record** hand-labelled gold set (`goldset/firm_type_goldset.jsonl`) evaluates the firm-type classifier. Full run: `python scripts/eval_goldset.py` → `docs/evidence/firmtype-goldset-eval.json`.

| Metric | Value | Reading |
|---|---|---|
| **Precision** | **1.00** | of the firms we shipped as family offices, **100% really are** |
| **False-positive rate** | **0.00** | **zero** non-FOs classified as FOs — the domain-critical guarantee |
| Recall | 0.44 | of the real FOs in the set, we caught 44% |
| False-negative rate | 0.56 | we missed 56% — see below |
| Accuracy | 0.64 | |
| Type accuracy | 0.57 | of correctly-qualified FOs with a known type, SFO/MFO correct 57% |

**Interpretation — a deliberate precision-over-recall tradeoff.** In this domain the deadly error is a false *positive* (presenting an unconfirmed firm as a proven family office — "the most serious error"). The classifier's **false-positive rate is zero**: it never ships a non-FO. The cost is recall — the 9 false negatives are **exactly the famous single-family offices that hide** (Walton Enterprises, Bezos Expeditions, Kirkbi, Mousse Partners, DFO Management, Builders Vision, Veritable, Korys, Financière Agache): no SEC filing, no adviser registration, no resolvable public website, so no free-tier authoritative evidence. Per the inclusion standard we **reject rather than guess**. This is the right tradeoff for decision-grade intelligence: a missed real FO costs a lead; a shipped fake FO costs the client's trust.

**Root cause of the false negatives:** free-tier verification scarcity, not a classifier logic error — the same scarcity quantified in the discovery report. **Improvement path:** paid data (ADV Part-1 bulk, a business-registry API) or reputable-press corroboration would recover several; documented in `KnownLimitations.md`.

*(Email verification gold set: not run — the delivered records carry firm-level contact, not principal emails, so there was nothing to measure yet; see KnownLimitations.)*

## 5. Email verification (honest by design)

We do **not** perform SMTP RCPT probing: from free/cloud IPs it is unreliable (greylisting → false undeliverables; catch-all domains → false deliverables) and treated as abusive (blacklisting risk). Instead, verification uses syntax + MX/domain liveness + role/pattern heuristics, and where genuine deliverability cannot be established on free tooling, the value is left blank and marked `could_not_verify`. A guessed value dressed as "verified" is never shipped; an honest blank is. (Gate-review A8.)

## 6. Two layers tested (Wave 3)

The dataset and the deployed answer are separate failure surfaces. Wave 3 adds a RAG evaluation harness measuring answer faithfulness and abstention on unanswerable queries, with real logged live queries — because testing the records does not test the answers.
