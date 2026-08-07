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
- The pool is **SEC-heavy** (regulatory lens is the most productive). The final-55 selection applies a per-source cap so the *shipped* file is not source-dominated (see the release policy in `docs/Validation.md` and `KnownLimitations.md`).
- 990-PF returns many non-family-office entities (religious/educational/benefit orgs); these are filtered by validation, not by discovery.

## 6. Enrichment (Wave 2)

Each candidate is enriched with **authoritative** facts, each snapshotted (content hash) for reproducible provenance:

- **SEC submissions** (`data.sec.gov/submissions`) — for any candidate with a CIK: legal name, business address, **firm phone**, EIN, former names, and a public-company flag (tickers/exchanges → reject).
- **IAPD / Form ADV** (`api.adviserinfo.sec.gov`) — the investment-adviser registration record. Because IAPD (IARD) is a **different filing system from EDGAR 13F**, it is a genuinely *independent* authoritative source for a firm discovered via 13F. Its registered aliases frequently state the family-office nature and single/multi type (e.g. "PATHSTONE FAMILY OFFICE, LLC"). A fuzzy **name-match guard** prevents ever attaching a different firm's record.
- **Firm website** — resolved via Wikidata P856 (for directory firms); homepage + `/about` parsed for family-office language, description, and AUM. (DuckDuckGo search was trialled to find sites for firms without a Wikidata URL but rate-limits too aggressively for bulk use — documented, not used.)
- **Wikipedia intro** — cited **background only**, never as FO-verification (discovery-only).
- **GDELT per-firm** — recent dated signals (sparse for private offices; honest blanks over filler).

## 7. Validation (Wave 2)

- **Firm-type classification** (`validation/firm_type.py`) enforces `config/inclusion_standard.md`: a firm qualifies only with **affirmative family-office evidence from an authoritative source** (SEC 13F self-identification, IAPD/ADV alias, or firm website) — never a name alone or a discovery-only reference. Non-qualifying orgs (public companies, funds, banks, pensions, religious/educational/network entities, individual trustees) are rejected with a reason recorded for the discovery report. Type is SFO/MFO from explicit language, honest **Undetermined** otherwise; **High** confidence requires two independent authoritative sources.
- **Gold-set evaluation** (`validation/goldset.py`, `docs/evidence/firmtype-goldset-eval.json`): a machine-drafted gold set (DRAFT, pending human review/confirmation) measures accuracy/precision/recall/**FP-rate**/FN-rate/confusion. In this domain the deadly error is a false *positive* (a non-FO shipped as an FO), so precision is the headline.
- **Release gate + selection** as in `docs/Validation.md`. Discovery vs verification are kept separate in every record; a firm discovered via 13F full-text search and verified via the distinct IAPD/submissions records + firm site is a multi-verified record, not a "same source" one.

## 8. The scarcity finding (evidence-backed)

Verified US family offices concentrate overwhelmingly in SEC data on free tiers. Non-SEC verification is genuinely scarce: bulk web search rate-limits, most single-family offices have **no public website** (Walton, Bezos, Mousse…), and even Form ADV is SEC-based. This is quantified in the discovery report (`docs/evidence/dataset-discovery-report.json`): of 192 discovered, the majority are rejected for no authoritative FO evidence or as non-FOs, leaving a smaller decision-grade set — exactly the market reality the assessment is built around. We document this rather than manufacture diversity or weaken validation.
