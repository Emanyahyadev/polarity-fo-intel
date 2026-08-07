# Validation

How the system decides what is trustworthy enough to ship, and how well that decision works. Following **How We Work**, validation is a distinct build type from the production pipeline and is judged on *measured* evidence (a gold set, false-positive / false-negative rates), not throughput.

## 1. Two build types, two evidence standards

- **Production systems** (discovery, enrichment, retrieval, serving) — judged operationally: do they run end-to-end without silent failure, and how do they behave under load/edge cases.
- **The validation layer** (firm-type classification, email verification, the release gate) — judged by measurement: accuracy, precision, recall, FP rate, **FN rate**, confusion matrix, against a machine-drafted gold set (DRAFT, pending human review/confirmation). A false negative (a bad value we labelled good) is the deadly error because it ships downstream with the system's confidence.

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

A **25-record** machine-drafted gold set (DRAFT, pending human review/confirmation; `goldset/firm_type_goldset.jsonl`) evaluates the firm-type classifier. Full run: `python scripts/eval_goldset.py` → `docs/evidence/firmtype-goldset-eval.json`.

| Metric | Value | Reading |
|---|---|---|
| **Precision** | **1.00** | of the firms we shipped as family offices, **100% really are** |
| **False-positive rate** | **0.00** | **zero** non-FOs classified as FOs — the domain-critical guarantee |
| Recall | 0.50 | of the real FOs in the set, we caught 50% |
| False-negative rate | 0.50 | we missed 50% — see below |
| Accuracy | 0.68 | |
| Type accuracy | 0.50 | of correctly-qualified FOs with a known type, SFO/MFO correct 50% |

**Interpretation — a deliberate precision-over-recall tradeoff, with an operational recovery path.** In this domain the deadly error is a false *positive* (presenting an unconfirmed firm as a proven family office — "the most serious error"). The classifier's **false-positive rate is zero**: it never ships a non-FO. The cost is recall — the 8 false negatives are the famous single-family offices that hide from SEC signals: Walton Enterprises, Bezos Expeditions, KIRKBI, Mousse Partners, Builders Vision, Veritable, Korys, Financière Agache. The blocker is the *automated SEC-signal enricher*, not the firm.

**System recall ≠ classifier recall.** The gold-set number above measures the automated firm-type classifier **in isolation**. The delivered *system* recovers **4 of these 8** — KIRKBI, Korys, Financière Agache, Builders Vision — through the non-SEC directory-discovery path (D24), verified against each firm's **own website** with an explicit single-family quote. So classifier recall is 8/16 = 0.50, but **system recall is 12/16 = 0.75**. The remaining 4 (Walton Enterprises, Bezos Expeditions, Mousse Partners, Veritable) have no free-tier authoritative site and are honestly **excluded — reject rather than guess**.

**Root cause of the classifier false negatives:** free-tier verification scarcity, not a classifier logic error. **Improvement path:** fold the website-recovery path into the eval harness to report system recall directly; paid data (ADV Part-1 bulk, a business-registry API) would recover the last 4. Documented in `KnownLimitations.md`.

*(Email verification gold set: not run — the delivered records carry firm-level contact, not principal emails, so there was nothing to measure yet; see KnownLimitations.)*

## 5. Email verification (honest by design)

We do **not** perform SMTP RCPT probing: from free/cloud IPs it is unreliable (greylisting → false undeliverables; catch-all domains → false deliverables) and treated as abusive (blacklisting risk). Instead, verification uses syntax + MX/domain liveness + role/pattern heuristics, and where genuine deliverability cannot be established on free tooling, the value is left blank and marked `could_not_verify`. A guessed value dressed as "verified" is never shipped; an honest blank is. (Gate-review A8.)

## 6. Two layers tested (Wave 3)

The dataset and the deployed answer are separate failure surfaces. Wave 3 adds a RAG evaluation harness measuring answer faithfulness and abstention on unanswerable queries, with real logged live queries — because testing the records does not test the answers.
