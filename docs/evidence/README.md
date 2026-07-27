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

## Artifact index

Present now (Wave 1):

| Artifact | Category | Claim it backs |
|---|---|---|
| `01-discovery-source-distribution.csv` | pipeline | discovery is genuinely multi-source |
| `01-discovery-harvest-summary.json` | pipeline | per-source yields + resolution actions |
| `01-harvest-discovery.log` | pipeline log | the harvest ran (incl. GDELT 429 recorded, not swallowed) |
| `02-entity-resolution-decisions.jsonl` | merge decisions | every merge/kept-distinct decision + basis (no silent drops) |
| `run-manifest-discovery-*.json` | run manifest | ties the pool to git commit + schema/pipeline version + counts |

Planned (filled in as later waves ship):

| Artifact | Category | Claim it backs |
|---|---|---|
| `firmtype-goldset-eval.json` | validation report | firm-type accuracy/precision/recall/FP/FN + confusion matrix |
| `email-goldset-eval.json` | evaluation metrics | email verification FP/FN |
| `audit-sample.csv` | audit trail | findings govern releases (withheld values) |
| `abstention-eval.jsonl` | sample queries | grounding control abstains on unanswerable queries |
| `live-query-transcript.md` + PNGs | screenshots | live system answers real queries |
| `deployment.md` + health check | deployment | live URL is up |
| `failure-cases.md` | failure cases | known mis-handled cases + responses |
