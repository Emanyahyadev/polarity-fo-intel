# family_offices_pending_review.csv

285 candidates that were force-merged directly into `family_offices.csv` on
2026-08-11 (commits `127e4d3`, `219f35e`) without going through
`classify()`/`ReleaseGate` — 282 of them carry explicit "not independently
verified" / "Type inferred ... not independently verified" language in their
own `classification_evidence` field, self-admitting they were never checked.

They are **not** part of the delivered dataset. `family_offices.csv` /
`.xlsx` / `data/final/records.json` contain only records that independently
cleared `ReleaseGate` (G1-G9) — see `docs/Stage2Status.md` and
`src/fointel/validation/gates.py`.

This file exists so the candidates aren't lost, and so their status is
visible rather than hidden — not as a second, lower-bar version of the
deliverable. To promote any of these into the real dataset, run them through
`scripts/reverify_merged_candidates.py`-style enrichment against the actual
gate, same as every other record in `family_offices.csv`.
