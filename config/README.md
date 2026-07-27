# config/ — static configuration assets

Runtime settings live in `src/fointel/config.py` (env-driven). This directory holds
**static config data** referenced by the pipeline, added as the build progresses:

- `sectors.yaml` — controlled vocabulary for `investing_sectors` (the 20-sector taxonomy
  from the reference sample, normalised).
- `seed_queries.yaml` — news/press discovery seed queries.
- `inclusion_standard.md` — the human-authored minimum bar a firm must clear to count
  toward the 50 (the standard the pipeline enforces).
