# Stage-2 Corrections — Implementation Report

Applies the corrections accepted from the Stage-1 review to the repository at
`polarity-fo-intel`. Scope confirmed by the candidate: **Option 1** (engineering
corrections verified from the repo), **Option 2** (gold-set review worksheet for the
candidate), **Option 4** (remove machine-derived time estimate; provide methodology +
template). Option 3 (the extended contact pipeline) was **not** requested.

## Corrections implemented

### 1. Compound aggregation — decompose, never drop a part (#08)
`_aggregate_answer` in `src/fointel/rag/answer.py` was refactored to answer a
compound count-AND-total question deterministically: "how many multi-family offices
and their total 13F securities" now returns **both** parts, with a `decompose`
trace (`mode="compound"`, `compute.parts` of length 2). Single-branch count/total
behaviour is unchanged (regression-tested).

### 2. Universal-coverage claims — truthful counts, not implied "yes" (#06)
- New `_universal_claim_answer` in `answer.py`: an all/every-claim ("every family
  office has a principal email") is answered with a whole-dataset coverage count
  (`0 of 61`), never with a record listing that implies "yes". Unrecognised
  universals safely fall through to normal (or abstain) handling.
- `scripts/eval_rag.py` QUERIES extended to cover the previously-missing classes
  (`count`, `total`, `compound`, `universal`, `off-topic-aggregate`) and reports
  per-class coverage. Result: **42/42 = 1.0**.

### 3. Principal role labels — bounded by the proving source (#10)
- New `src/fointel/rag/roles.py::principal_role()`. A "principal" is labelled from
  the verification source that actually proved the person: filing signatory (13F),
  registered person (Form ADV), listed person (website), etc. It never asserts a
  role ("owner", "CEO", "decision-maker") the evidence did not establish.
- Surfaced in query cards, the data Directory, and the extractive answer.
- Distribution across the 38 named principals: 25 filing signatory (13F), 10
  registered person (ADV), 3 listed person (website).

### 4. Whole scoreboard in the published deliverables (#05)
- README deliverables table now cites the **complementary** metrics that were
  previously only in `Validation.md`: precision 1.00, FP-rate 0.00 · recall 0.50,
  accuracy 0.68, 8 FNs, system recall 0.75.
- Corrected "hand-labelled truth" claims in `README.md`, `docs/Methodology.md`,
  `docs/Validation.md` → **machine-drafted gold set (DRAFT, pending human
  review/confirmation)**, matching the gold set's actual header.

## Human-judgment deliverables (assigned to the candidate, not auto-filled)

### Gold-set review worksheet (Option 2)
- New `scripts/gen_goldset_worksheet.py` deterministically renders every gold-set
  record (25) into `goldset/review_worksheet.md`, showing the machine-drafted
  answer, whether the firm is in the delivered 61, its served type, and served
  evidence, plus blank review columns for the candidate. It does **not** modify the
  gold-set file and confirms nothing.

### Effort reporting (Option 4)
- `docs/BuildSessionSummary.md` rewritten: the machine-derived "18–20 hours" figure
  (a commit-timestamp span, not effort) is **removed**, and first-person claims
  replaced by repo-supported, attribution-free statements.
- New `docs/effort-report.md`: the methodology (why timestamps are not effort) and a
  blank per-phase template the candidate fills with her own recorded figures.

## Verification
- Full suite: **165 passed, 1 skipped** (baseline 159 + 6 new tests).
- `scripts/eval_rag.py`: **42/42 = 1.0** across 14 labelled classes.

## Files changed
- `src/fointel/rag/answer.py`, `src/fointel/rag/roles.py` (new), `src/fointel/serve/app.py`,
  `src/fointel/serve/web/index.html`, `scripts/eval_rag.py`, `scripts/gen_goldset_worksheet.py` (new),
  `tests/test_stage2_operate.py`, `README.md`, `docs/BuildSessionSummary.md`,
  `docs/effort-report.md` (new), `docs/Methodology.md`, `docs/Validation.md`,
  `goldset/review_worksheet.md` (new), `docs/evidence/rag-abstention-eval.{json,md}`.

## Awaiting the candidate's review
- Confirm the gold set (via `goldset/review_worksheet.md`), then update
  `firm_type_goldset.jsonl`.
- Fill `docs/effort-report.md` with verified effort figures.