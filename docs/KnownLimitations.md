# Known Limitations

Honest limits of the current build. Stating them is the point — hidden uncertainty is the failure mode this project is designed to avoid.

## Discovery & coverage
- **Invisible SFOs.** A family office with no filing, no foundation, no notable-reference listing, and no press is unreachable by all four lenses. This is an inherent free-tier limit, not a bug.
- **SEC-heavy pool.** The regulatory lens is the most productive (~62% of the raw pool). The *shipped* 50 is balanced by a per-source cap (see `Validation.md` / release policy), but discovery itself skews SEC.
- **990-PF noise.** The tax-exempt lens surfaces many non-family-office entities (religious, educational, benefit/union plans). Validation filters them; discovery does not.
- **News discovery is weak.** GDELT's generic "family office" query is noisy/non-English; news earns its place as a per-firm *signals* source, not bulk discovery.
- **Notability bias.** Wikipedia/Wikidata list only well-known offices, skewing the curated lens toward large, famous (often foreign) SFOs.
- **Non-US coverage.** The product targets the US market, but the curated lens pulls foreign offices (Denmark, France, Monaco). The final-50 selection applies US weighting; foreign marquee SFOs are included only with justification.

## Validation
- **Email deliverability is not fully verifiable on free tooling.** We deliberately avoid abusive SMTP probing; some contact emails will be honest `could_not_verify` blanks rather than "verified."
- **Gold set is small (25–30).** Metrics carry wide confidence intervals; reported with n and interpreted cautiously.
- **Firm-type at the edges.** SFO vs MFO and holdco vs FO are genuinely ambiguous for some firms; these are labelled `Undetermined` or routed to manual review rather than guessed.

## Data model (to be revisited)
- **Single principal per record.** A family office often has several relevant decision-makers (CIO, Head of Direct Investments, founder). A `contacts: list[...]` model is planned; noted so the limitation is explicit, not hidden.
- **AUM is a free-text string** with provenance, not a normalised numeric with an as-of date. Adequate for intelligence; not yet analytic-grade.

## Reproducibility
- **Working snapshots are gitignored** (bulky, third-party, PII). Provenance carries url + fetched_at + content_hash in the committed dataset; the snapshots backing the released 50 are bundled into `docs/evidence/` at export so the committed repo is self-contained for the delivered records. The full candidate-pool raw content is regenerable via `run_pipeline.py`, not archived.
- **Live sources drift.** Re-running months later yields a *different* pool (new filings, GDELT's sliding window). The method is reproducible; the exact records are reproducible only against the retained snapshots + the run manifest's git commit.

## Licensing / ToS
- **Wikipedia text is CC-BY-SA.** If Wikipedia prose is reused in enrichment it requires attribution/share-alike; we prefer to derive facts and cite rather than copy text. ProPublica and SEC/IRS usage terms are respected; Google News RSS was rejected on ToS grounds.

## Scale
- Synchronous, single-threaded HTTP; SQLite single-writer (dev); GDELT hard-capped at ~1 req/5s. Fine at 50 records. Beyond ~1k firms this needs async workers, the Postgres backend (already behind the Repository interface), a job queue, and incremental refresh. The DB swap is a config change (`DATABASE_URL`); the concurrency redesign is not yet done.

## Backends / infrastructure
- **Postgres/Supabase backend** is implemented and unit-testable but is validated against a live instance only at deploy (its roundtrip test is skipped unless `TEST_DATABASE_URL` is set). SQLite is the tested backend at this scope.
