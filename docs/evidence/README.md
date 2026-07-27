# Evidence Directory

Every significant claim in this repository's documentation must link to a reproducible artifact here. If a claim has no evidence, it is downgraded to an explicitly-labelled assumption or removed.

## Convention

- One artifact per claim, named `NN-short-slug.<ext>` (e.g. `01-discovery-source-distribution.csv`).
- Machine-produced artifacts (logs, metric outputs, query transcripts) are preferred over prose.
- Each artifact records **how to reproduce it** (the command or script + inputs) in a header comment or an adjacent `.md` note.
- Screenshots (deployment, live queries) are timestamped and paired with the exact query/URL used.

## Evidence categories (every significant engineering claim maps to one)

- **Pipeline logs** — end-to-end run logs proving the file is pipeline-produced.
- **Validation reports** — the gold-set ML evaluation (metrics + failures + root cause).
- **Evaluation metrics** — machine-readable metric outputs (JSON) behind every reported number.
- **Sample retrieval queries** — real queries + returned evidence + whether the system answered or abstained.
- **Screenshots** — deployment + live queries (timestamped, paired with the exact query/URL).
- **Deployment evidence** — build logs, the live URL, health check output.
- **Rejected records / audit trail** — values withheld by the gates (findings govern releases).
- **Failure cases** — edge cases the pipeline/validation/RAG mis-handled, and how we responded.

## Artifact index (filled in as waves complete)

| # | Category | Claim it backs | Artifact | Produced by |
|---|---|---|---|---|
| 01 | pipeline log | Discovery is genuinely multi-source | `01-discovery-source-distribution.csv` | pipeline stats |
| 02 | validation report | Firm-type classifier accuracy/precision/recall/FP/FN + confusion matrix | `02-firmtype-goldset-eval.json` | `validation/goldset.py` |
| 03 | evaluation metrics | Email verification FP/FN | `03-email-goldset-eval.json` | `validation/goldset.py` |
| 04 | audit trail | Findings govern releases | `04-audit-sample.csv` | release gate |
| 05 | sample queries | Grounding control abstains on unanswerable queries | `05-abstention-eval.jsonl` | RAG eval harness |
| 06 | screenshots | Live system answers real queries | `06-live-query-transcript.md` + PNGs | manual, on deployed URL |
| 07 | pipeline log | Pipeline reproduces the 50 | `07-pipeline-run.log` | `scripts/run_pipeline.py` |
| 08 | deployment | Live URL is up | `08-deployment.md` + health-check output | HF Space |
| 09 | failure cases | Known mis-handled cases + responses | `09-failure-cases.md` | manual review |
