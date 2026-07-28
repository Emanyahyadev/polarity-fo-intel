# Build Log

Chronological record of work sessions, decisions made in the moment, and judgment calls.
Doubles as evidence of incremental (not hand-assembled) work and as the source for the
required Build Session Summary. Times are approximate, in the candidate's local timezone.

---

## Session 1 — Wave 1: Foundation + Architecture (Mon)

**Goal.** Stand up a production-shaped scaffold and lock the architecture before writing
discovery connectors, per the architecture checkpoint.

**Done.**
- Repo scaffold + git init (branch `main`), layered package under `src/fointel/`.
- Data model (`schema.py`): `FamilyOfficeRecord` with per-cell `Provenance` (Rule 1),
  `qualifies()` firm-type gate (Rule 2), `AuditEntry` for withheld values (findings govern
  releases), `Signal` for recent dated activity.
- Discovery contract (`discovery/base.py`) separating discovery from proof.
- Config (`src/fointel/config.py`) — env-driven, no secrets in code; static assets under `config/`.
- Made the package installable (`pyproject.toml`, `pip install -e .`); 6 schema unit tests pass.
- Docs: Architecture, DecisionLog (D1–D9), Tradeoffs (T1–T5), evidence-dir convention.
- Python 3.12 venv + Wave-1 deps installed and import-verified.

**Judgment calls this session (AI built, human decided).**
- Chose 3 discovery classes (SEC ADV / 990-PF / News) over a broader crawl — clears the
  multi-source bar without spreading verification too thin. (DecisionLog D2)
- Made SQLite + local embeddings the default over hosted services — reproducible & free. (D1)
- Private repo due to PII in the deliverable. (D4)
- Deferred all connector/RAG/UI implementation until architecture is approved.

**Open (need candidate input at checkpoint).**
- Git identity + AI co-author trailer preference → no commits made until set (D8).
- Deployment target (D9) — decided at Wave 3.

**Next.** On approval: implement the discovery sources and harvest a ~4× candidate pool.

---

## Session 2 — Wave 1: Approved-with-tweaks refinements (Mon)

**Goal.** Fold the candidate's targeted engineering improvements into the design as final
decisions, before writing connectors.

**Done.**
- Discovery: added a 4th non-regulatory lens (FO directories/associations); documented why
  each of the 4 sources exists and what evidence it contributes. (DecisionLog D2)
- Discovery/verification separation made structural: `discovery_source` vs
  `verification_sources[]` + `independence_warnings()` when they overlap without justification.
- Field-level confidence: each important field carries confidence derived from its provenance;
  `record_confidence` = weakest-link across identity anchors. Confidence cannot be inflated
  independently of evidence. (D9)
- Storage behind a `Repository` interface; SQLite impl now, Postgres/Supabase at deploy via
  `DATABASE_URL` — no business-logic change. (D5)
- Structured observability (`observability.py`) across 5 channels; JSON logs, no silent
  failures. (D10)
- Release gates specified (8 mandatory checks) and gold-set target raised to 25–30 with a full
  ML-eval report format. (D7, D11)
- RAG updated to hybrid retrieval (vector + BM25 + metadata). (D8)
- DecisionLog rewritten to the 6-element standard (Decision/Reasoning/Alternatives/Tradeoffs/
  Risks/Future improvements); evidence catalogue expanded to 9 categories.
- Git identity set (Emanyahyadev); no AI attribution in-repo per directive, disclosed in the
  build summary instead. (D12) · Deploy target fixed to HF Spaces Docker. (D13)

**Judgment calls this session.**
- Kept the ceiling at 4 discovery lenses — diversity of lens over quantity of connectors.
- Chose JSON-payload + indexed-columns storage so the SQLite→Postgres swap is a drop-in.
- Derived confidence from provenance rather than a free-standing field, to make inflation impossible.

**Tests.** 13 passing (schema rules of proof, field confidence, discovery/verification
independence, repository roundtrip + dedup + qualifying filter).

**Next.** Implement the 4 discovery connectors + candidate-pool harvest with provenance and logs.

---

## Session 3 — Wave 1: Discovery connectors + candidate pool (Mon)

**Goal.** Build the 4 discovery sources and harvest a diverse, provenance-tagged candidate pool.

**Tested reality before coding (How We Work).** Probed all source APIs live first:
- SEC EDGAR full-text search (`efts.sec.gov`) → 892 "family office" 13F filers; `data.sec.gov/
  submissions/{CIK}.json` gives authoritative name/address/**phone**. High-signal. ✅
- ProPublica Nonprofit Explorer → works but noisy for FOs (most FOs are for-profit). Diversity lens.
- **Google News RSS → its ToS forbids non-personal/commercial use** → pivoted news to **GDELT**.
- **GDELT** → works but rate-limits 1/5s, and the generic "family office" query is a WEAK discovery
  channel (mostly non-English noise). Repositioned news as a **signals** source (per-firm queries in
  enrichment), not bulk discovery — an honest empirical finding, documented.
- Wikipedia `Category:Family_offices` (9) + **Wikidata** instances of family office `Q751314` (14) →
  clean, ToS-safe, high-quality (mostly SFOs). Used both for the curated-directory lens.

**Built.**
- Shared `http.py`: descriptive UA, tenacity retries, per-source throttle (GDELT 6s), no silent failures.
- 4 connectors: `sec_edgar.py`, `irs_990pf.py`, `news.py` (GDELT), `directory.py` (Wikipedia+Wikidata).
- `harvest.py` orchestrator (per-source limits, cross-source overlap, distribution report) + `scripts/harvest.py`.
- Honesty fix: renamed source label `SEC_ADV` → `SEC_EDGAR` (we use EDGAR 13F/SC filings, not IARD Form ADV).

**Harvest result (evidence: docs/evidence/01-*).** 191 unique candidates — SEC 119, 990-PF 50,
Directory 22, News 0. Real, verifiable firms incl. Duquesne Family Office (Druckenmiller SFO),
Pathstone, Veritable, Walton Enterprises, Bezos Expeditions, Kirkbi. Pool is pre-validation; Wave 2
qualifies + balances the final-55 source mix (SEC is 62% of the raw pool but the selection controls the
delivered distribution).

**Judgment calls.** Kept news despite 0 discovery (honest, documents a real limitation; it earns its
place as the signals engine). Capped noisy 990-PF at 50; pulled 120 from high-signal SEC. A regression
test caught a name-extraction bug (leading "The" swallowed) before it shipped.

**Tests.** 16 passing (added discovery pure-function tests).

**Next.** Wave 2 — enrichment (SEC submissions, firm sites, per-firm GDELT signals) + validation layer
(firm-type classifier, email verification), release gates, gold-set metrics, and the final 55.

---

## Session 4 — Architecture Gate Review remediation (Mon)

**Goal.** Close every mandatory item from the gate review before any production data is created.
Default assumption during review: "not ready." Each fix shipped with tests + docs + evidence + a commit.

**Done (commit-by-commit).**
- Provenance enforcement (cfb1c16): construction-time invariant (no populated + could_not_verify)
  + `provenance_violations()`; Provenance gains fetched_at/content_hash/snapshot_path.
- Entity resolution (30b834d): conservative `norm_name`; `EntityResolver` merges only on shared
  identifier or name+geo, flags fuzzy dups kept-distinct; every decision logged. Live: 192 firms,
  0 silent merges, 3 flagged (a Porfolio/Portfolio typo, MSGE/SPHR).
- Inclusion standard (bcbf581): `config/inclusion_standard.md`; `qualifies()` now hinges on
  FO-evidence, decoupled from SFO/MFO/Undetermined sub-type.
- Release gate (b773b06): `ReleaseGate.publish()` single authority, 9 gates, core invariant test
  (audited value never shipped). Caught a real bug: `name` is a reserved LogRecord attr.
- Reproducibility (0df0063): `evidence.py` snapshots (sha256) + run manifest (git commit, versions,
  counts); `http.get_with_evidence`.
- Repo integrity (6612a11): real `SupabaseRepository` (lazy psycopg, clear error, no dangling
  import); canonical `scripts/run_pipeline.py`; created Methodology/Validation/KnownLimitations;
  fixed README refs.
- Source diversity (490e20b): `select_final()` caps any discovery source at ~40% of the shipped N,
  relax only with logged justification.
- Observability (1c33717): connectors on the `discovery` channel with skip logging; no silent skips.
- Integration tests (b08a3df): mocked-source end-to-end (discovery→resolve→persist; gate→selection).
- Docs sweep: Architecture reconciled (4 lenses = 3 discovery + news-as-signals; SEC EDGAR not ADV;
  9 gates; no SMTP probing), DecisionLog D14–D19, evidence catalogue, this log.

**Judgment calls.** Chose to refuse the original certification and fix first, rather than proceed on
unproven gating/provenance. Implemented a real Postgres backend rather than reword the claim.
Kept news despite 0 discovery — honest, and it earns its place as the signals engine.

**Tests.** 48 passing, 1 skipped (Postgres roundtrip, gated on TEST_DATABASE_URL).

**Next.** Final gate: full suite + adversarial self-review + certification decision.
