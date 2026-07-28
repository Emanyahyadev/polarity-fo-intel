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
| `02-entity-resolution-decisions.jsonl` | merge decisions | every merge/kept-distinct decision + basis (no silent drops) |
| `dataset-discovery-report.json` | pipeline | 398 discovered → 189 qualified → 68 released → 55 selected, with rejection reasons |
| `firmtype-goldset-eval.json` | validation report | firm-type precision 1.00 / FP-rate 0.00 / recall 0.50 + the false negatives |
| `rag-abstention-eval.json` + `.md` | RAG eval | grounding/abstention 29/29 on labelled queries incl. adversarial in-vocabulary probes ("pizza office", "office space", "family offices on the moon") |
| `run-manifest-discovery-*.json` / `run-manifest-dataset-*.json` | run manifest | ties pool + release to git commit + schema/pipeline version + counts |
| `live-url-query-transcript.json` + `.md` | deployment | live URL verified — `/health` = 55 records + 6 real queries (4 answered with grounded records, 2 correct abstentions) |

Planned / pending:

| Artifact | Category | Status |
|---|---|---|
| live-URL screenshot | screenshots | optional visual capture of the live UI (machine-readable transcript already present above) |
| `email-goldset-eval.json` | evaluation metrics | not run — records are firm-level, no principal emails to verify yet |
