# Methodology

How the system discovers, resolves, and (in Wave 2) enriches and validates family-office records. Written so another engineer can reproduce it without talking to us. Wave 1 covers discovery + entity resolution; enrichment and validation methodology are appended as those stages ship.

## 1. Discovery — four lenses, kept separate from proof

Where you look determines what you can find; verification cannot recover firms a source never showed you. So we discover from four deliberately different lenses and keep *discovery* strictly separate from *verification* (a source used to find a firm is not, by itself, proof of anything about it).

| Lens | Source | Why it exists | Evidence it contributes | Status |
|---|---|---|---|---|
| Regulatory | **SEC EDGAR** full-text search over 13F/SC filings mentioning "family office" | real investment entities managing family wealth; high-signal | firm name, CIK, business location; (enrichment) authoritative address/phone via `data.sec.gov/submissions` | active (120/run) |
| Tax-exempt | **IRS 990-PF** via ProPublica Nonprofit Explorer | surfaces families behind private foundations that filings/directories miss | family/foundation name, EIN, city/state | active but noisy (50/run) |
| Curated | **Wikipedia `Category:Family_offices` + Wikidata `Q751314` instances** | notable, verifiable offices — heavily single-family | firm name, country, an article for enrichment. **DISCOVERY ONLY — never used to verify** (community-edited) | active (22/run) |
| Media | **GDELT** DOC API | intended for non-filing SFOs + recent dated signals | (enrichment) recent dated activity per firm | signals-primary; weak for bulk discovery |

**Empirical finding, not papered over:** GDELT's generic "family office" query returns mostly noise/non-English coverage, so news is repositioned to a *per-firm signals* source in enrichment rather than a bulk discovery channel. Google News RSS was rejected outright — its terms forbid non-personal/commercial use.

Rate/politeness: all sources use a shared HTTP client with a descriptive User-Agent, tenacity retries, and per-source throttling (GDELT ≥5s). A source that fails is logged and skipped (its failure appears in the run manifest), never allowed to sink the harvest.

## 2. Entity resolution — evidence-based, never silent

Candidates are de-duplicated by `EntityResolver`, not by a lossy name key:

- **Merge** only on a shared strong identifier (CIK / EIN / QID / domain) **or** exact conservatively-normalised name + compatible geography + no identifier conflict.
- A merely similar name (high fuzzy score) is **flagged `possible_duplicate_kept_distinct`** for manual review — never auto-merged, because a false merge silently deletes a real firm.
- Conservative name normalisation strips only legal-entity suffixes (LLC/LP/Inc), never distinguishing words ("Blue Capital" ≠ "Blue Partners").
- **Every** decision (new / merge / kept-distinct) is logged with its basis and written to `docs/evidence/02-entity-resolution-decisions.jsonl`. Cross-source discovery is captured in each firm's `discovery_sources`.

Live run (see the run manifest): 192 firms, 0 silent merges, 3 near-duplicates flagged (a `Porfolio`/`Portfolio` typo, MSGE/SPHR ticker variants) — exactly the pathological cases blind dedup would have mangled.

## 3. Qualification and source roles (policy)

Inclusion is governed by `config/inclusion_standard.md` and enforced by the release gate (`docs/Validation.md`). In short: a firm qualifies only with affirmative evidence it is a family office (Rule 2); Wikipedia/Wikidata are discovery-only and can never verify; discovery and verification sources must be independent unless justified.

## 4. Reproducibility

Every run writes a manifest (`docs/evidence/run-manifest-*.json`) tying the pool to the exact git commit, schema version, pipeline version, timestamps, and counts. Retrieved source content is content-addressed (sha256) so a claim can be reproduced or shown to have drifted (`fointel.evidence`).

## 5. Material blind spots (discovery)

- A family office with **no filing, no foundation, no notable-reference listing, and no press** is invisible to all four lenses — an inherent limit of a free-tier approach.
- The pool is **SEC-heavy** (regulatory lens is the most productive). The final-50 selection applies a per-source cap so the *shipped* file is not source-dominated (see the release policy in `docs/Validation.md` and `KnownLimitations.md`).
- 990-PF returns many non-family-office entities (religious/educational/benefit orgs); these are filtered by validation, not by discovery.

*(Enrichment and validation methodology — SEC submissions, firm-site parsing, per-firm GDELT signals, firm-type classification, email verification — is documented here as Wave 2 ships each stage.)*
