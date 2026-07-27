# Decision Log

Every decision records: **Decision · Reasoning · Alternatives considered · Tradeoffs · Risks · Future improvements.** Written so another senior engineer can reproduce the repository without speaking to us.

---

### D1 — Stack: Python 3.12 · repository-abstracted storage · local embeddings · FastAPI + static UI · free-tier LLM
- **Decision.** Python 3.12 (via `py -3.12`; bare `python` is a broken Windows Store stub). Storage behind a `Repository` interface (SQLite dev → Postgres/Supabase deploy, see D5). `sentence-transformers/all-MiniLM-L6-v2` local embeddings. FastAPI + hand-built static UI. Free-tier hosted LLM (Groq or Gemini) for generation only.
- **Reasoning.** Everything free-tier and reproducible; local embeddings need no key/limits; FastAPI+static gives genuine presentation/retrieval separation the assessment scores.
- **Alternatives considered.** Streamlit (rejected: reads as a demo, blurs layer separation); hosted embedding API (rejected as default: key + rate limits, less reproducible); Node/Next (heavier, no Python data ecosystem).
- **Tradeoffs.** Local embeddings mean a heavier install (torch) but full reproducibility and no cost.
- **Risks.** torch may exceed a free host's build limits → mitigation in D5/D13. Python 3.14 also installed; we pin to 3.12 for wheel availability.
- **Future improvements.** Swap MiniLM for a larger embedding model if recall is weak; add a reranker.

### D2 — Discovery from four source classes: SEC ADV · IRS 990-PF · News · FO Directories
- **Decision.** Four discovery lenses — regulatory (SEC EDGAR Form ADV), tax-exempt (IRS 990-PF via ProPublica), media (news/press), curated (public FO directories/associations). Discovery kept separate from proof sources.
- **Reasoning.** One convenient source = automatic fail. Four independent lenses give genuine market discovery; 990-PF specifically surfaces single-family offices (families behind foundations) that filings and directories miss; news supplies the dated signals that drive commercial value; a directory lens cross-checks the others.
- **Alternatives considered.** 3 sources (sufficient but thinner diversity); a broad web crawl (rejected: unfocused, high noise, ToS risk); paid data vendors (rejected: free-tier constraint + a vendor's finished record demonstrates the vendor, not our system).
- **Tradeoffs.** More sources = more coverage but more surface to validate; four is the deliberate ceiling ("diversity of lens, not quantity of connectors").
- **Risks.** Discovery could still skew to one lens → we report the per-record discovery distribution and rebalance if skewed. Some directories are paywalled → we use only freely-accessible ones and document which.
- **Future improvements.** Add state business-registry and real-estate/philanthropy lenses for deeper SFO coverage.

### D3 — Prioritise verifiable qualification over SFO count
- **Decision.** Include a firm only with affirmative FO evidence; label SFO/MFO/Undetermined honestly; pursue SFOs but never inflate their count by relabelling.
- **Reasoning.** Candidate directive + the assessment: misclassification "costs more than an honest label," and presenting an unconfirmed firm as a proven FO is "the most serious error in this domain."
- **Alternatives considered.** Aggressive SFO-maximisation (rejected: relabelling risk = disqualification).
- **Tradeoffs.** Likely fewer SFOs than a dishonest file, but zero misclassification exposure.
- **Risks.** A thinner SFO share could read as "convenient sourcing" → we counter with the 990-PF SFO channel and an honest type distribution.
- **Future improvements.** Deepen SFO discovery channels to raise the honest SFO share.

### D4 — Repository is private, shared with the evaluator
- **Decision.** Private GitHub repo shared with optimize@falconscaling.com; raw scraped payloads gitignored.
- **Reasoning.** The deliverable contains real individuals' business contact PII; publishing it to a public repo is irresponsible. The assessment allows "public **or** shared."
- **Alternatives considered.** Public repo (rejected: PII exposure); public repo with scrubbed data (possible later as a portfolio fork).
- **Tradeoffs.** Slightly less open-portfolio optics for correct data handling.
- **Risks.** None material.
- **Future improvements.** Publish a PII-scrubbed public variant for portfolio use.

### D5 — Storage behind a Repository interface; Postgres/Supabase preferred, SQLite for dev
- **Decision.** All business logic depends on `store/Repository`. SQLite implements it locally; a Postgres/Supabase implementation is selected when `DATABASE_URL` is set. Records stored as JSON payload + indexed columns (ports to Postgres `jsonb`).
- **Reasoning.** Candidate directive: prefer Postgres/Supabase from the beginning; no DB-specific assumptions may leak. The interface makes migration a config change, not a rewrite.
- **Alternatives considered.** SQLite-only (rejected: doesn't meet the directive, weaker deploy story); Postgres-only from day one (rejected: slower local iteration, needs network for every test).
- **Tradeoffs.** A thin abstraction layer to maintain, in exchange for a zero-cost DB swap.
- **Risks.** Interface drift if a caller reaches around it → enforced by keeping concrete types out of signatures + tests on the interface.
- **Future improvements.** Add pgvector to move the semantic index into Postgres at scale.

### D6 — Per-cell provenance + audit trail; findings govern releases
- **Decision.** Every high-value cell carries `Provenance`; failed values are withheld and written to `data/audit/` as `AuditEntry`.
- **Reasoning.** Satisfies Rule 1 and proves validation *changed what we shipped*, not merely measured it.
- **Alternatives considered.** A single per-record source column (rejected: too coarse to defend a sampled cell).
- **Tradeoffs.** More columns / a provenance sheet, for full auditability.
- **Risks.** Provenance could go stale → each entry carries `checked_at`.
- **Future improvements.** Snapshot the source page (hash/archive URL) per cell.

### D7 — Explicit validation layer with a 25–30 record gold set and full ML metrics
- **Decision.** Hand-label a 25–30 record gold set for firm-type; report accuracy, precision, recall, FP rate, FN rate, confusion matrix, failure examples, root-cause, improvements. Separate gold set for email verification.
- **Reasoning.** How We Work distinguishes production systems (operational evidence) from validation layers (measured evidence vs a gold set); FN is the deadly metric.
- **Alternatives considered.** "We validated 50 records" prose (rejected: measures nothing); throughput reporting (rejected: wrong metric for a validation layer).
- **Tradeoffs.** ~1–2h human labelling, for the clearest top-tier differentiator.
- **Risks.** Small gold set → wide confidence intervals; we report n and interpret cautiously.
- **Future improvements.** Grow the gold set; add inter-rater checks.

### D8 — Grounding/abstention control enforced in code, over hybrid retrieval
- **Decision.** Hybrid retrieval (vector + BM25 + metadata filter, RRF-fused) → threshold + citation-required generation + post-hoc claim/cell check + abstention path. Not prompt-only.
- **Reasoning.** "Prompt instructions alone are not enough" is explicit; hybrid retrieval handles exact-match (names/places) and semantic queries together.
- **Alternatives considered.** Vector-only (rejected: misses exact names/filters); prompt-only grounding (rejected: unprovable).
- **Tradeoffs.** More retrieval machinery to build and test.
- **Risks.** Threshold mis-tuning → tuned against an eval set incl. unanswerable queries.
- **Future improvements.** Add a learned reranker and per-claim citation highlighting in the UI.

### D9 — Field-level confidence, derived from evidence
- **Decision.** Confidence is per-field, computed from each cell's provenance; `record_confidence` = weakest link across identity anchors. No independent confidence knob.
- **Reasoning.** Candidate directive; prevents inflated confidence — "confidence columns that never dip" is a fabrication tell the assessment calls out.
- **Alternatives considered.** Single record-level score (rejected: too coarse; hides weak cells).
- **Tradeoffs.** More columns in the delivered file (acceptable for an intelligence product).
- **Risks.** Mapping errors between fields and provenance keys → covered by tests.
- **Future improvements.** Calibrate confidence bands against the gold set.

### D10 — Structured observability from the start
- **Decision.** `observability.py` provides per-channel loggers (pipeline / validation / retrieval / api / deployment) writing human-readable console + JSON files. Every caught failure logs with context.
- **Reasoning.** Candidate directive + How We Work: no silent failures; the operate-unattended Stage 2 depends on this.
- **Alternatives considered.** `print` / ad-hoc logging (rejected: not queryable, easy to silence).
- **Tradeoffs.** A little setup up front.
- **Risks.** Log noise → levels (DEBUG to file, INFO to console) + rotation.
- **Future improvements.** Ship logs to a hosted sink; add trace IDs across layers.

### D11 — Mandatory release gates
- **Decision.** A record ships only if all gates pass (qualifies, classification evidence, discovery documented, verification documented, contradictions resolved, mandatory fields complete, validation status recorded, audit retained). Rejected values never enter customer records.
- **Reasoning.** Candidate directive; the gate is the single place that decides what a customer sees.
- **Alternatives considered.** Soft warnings (rejected: lets weak records leak through).
- **Tradeoffs.** May shrink the shippable set below 50 → we discover a ~4× pool to compensate.
- **Risks.** Over-strict gates starve the file → gate thresholds reviewed at the dataset checkpoint.
- **Future improvements.** Per-gate metrics on how many records each gate removes.

### D12 — Git: init immediately, milestone commits, never rewrite, no AI attribution
- **Decision.** Git initialised at the start; a commit per logical milestone with intent-describing messages; history never squashed or rewritten. Commits under the candidate's identity; no `Co-Authored-By` / AI branding in the repo (candidate directive). AI usage is disclosed honestly in the required Build Session Summary instead.
- **Reasoning.** Evaluators read history as an honesty signal; rewriting is prohibited. AI attribution kept out of the repo per candidate preference, while the build summary tells the truth (misrepresenting one's own contribution is disqualifying, so we do not claim "no AI").
- **Alternatives considered.** Per-commit AI trailer (declined by candidate); squashed history (prohibited).
- **Tradeoffs.** None material.
- **Risks.** Author name must be correct from commit 1 (no rewrite) → set before first commit.
- **Future improvements.** Signed commits.

### D13 — Deployment target: Hugging Face Spaces (Docker)
- **Decision.** Deploy the FastAPI + UI as a Docker Space on Hugging Face.
- **Reasoning.** Free, persistent public URL, no idle spin-down (a reviewer opening it gets a warm system), supports local embeddings.
- **Alternatives considered.** Render free (cold starts on idle); Fly.io (free allowance, more setup).
- **Tradeoffs.** Image build must fit Space limits → keep the image lean; precompute the index at build.
- **Risks.** torch image size → precompute embeddings at build, or fall back to a hosted embedding API if the image is too large.
- **Future improvements.** Custom domain; uptime monitoring.

---

*Decisions D14–D19 were added during the Architecture Gate Review remediation.*

### D14 — Evidence-based entity resolution; conservative name normalisation
- **Decision.** Merge candidates only on a shared strong identifier (CIK/EIN/QID/domain) or exact conservatively-normalised name + compatible geography + no id conflict. Similar names are flagged `possible_duplicate_kept_distinct`, never auto-merged. `norm_name` strips only legal-entity suffixes.
- **Reasoning.** The prior lossy dedup collapsed distinct firms ("Blue Capital" vs "Blue Partners") and silently dropped one via INSERT OR IGNORE (gate-review A4). A false merge deletes a real firm and corrupts the count + source diversity.
- **Alternatives considered.** Fuzzy auto-merge (rejected: false merges); name-only key (rejected: the original bug); no dedup (rejected: cross-source duplicates).
- **Tradeoffs.** Keeps a few genuine duplicates as "kept distinct" pending manual review, in exchange for zero silent data loss.
- **Risks.** Under-merging leaves near-dups (e.g. typo variants) → surfaced in the decisions log for a human.
- **Future improvements.** Address/domain-based clustering; a learned matcher.

### D15 — Release gate as the single publication authority; provenance enforced in code
- **Decision.** `ReleaseGate.publish()` is the only path to a released record; nine mandatory gates, all must pass. Provenance completeness (Rule 1) and the "no rejected value shipped" invariant (G9) are enforced by the gate + a construction-time schema validator, not documentation.
- **Reasoning.** "Findings govern releases" was prose with no enforcement (gate-review A1, A2). The gate makes it a checkable, tested property.
- **Alternatives considered.** Soft warnings (rejected: weak records leak); enforcing at construction (rejected: breaks incremental record building).
- **Tradeoffs.** May shrink the shippable set below 50 → mitigated by a ~4× discovery pool.
- **Risks.** Over-strict gates starve the file → gate outcomes are logged so removal rates are visible; thresholds reviewed at the dataset checkpoint.
- **Future improvements.** Per-gate removal metrics in the run manifest.

### D16 — Reproducible evidence retention + run manifest
- **Decision.** Content-address retrieved sources (sha256) with `fetched_at` in each cell's provenance; write a run manifest (git commit, schema/pipeline version, timestamps, counts) per run; bundle the snapshots backing the released 50 into `docs/evidence/` at export.
- **Reasoning.** Live sources drift; without retained content a claim cannot be reproduced months later (gate-review A3).
- **Alternatives considered.** URLs only (rejected: rot/drift); committing all raw content (rejected: bulky, PII, third-party).
- **Tradeoffs.** Snapshot storage + a small export-time bundle step, for genuine reproducibility of the delivered records.
- **Risks.** Working snapshots are gitignored → the committed repo is self-contained only for the bundled released 50 (documented in KnownLimitations).
- **Future improvements.** archive.org "Save Page Now" URLs for durable web references.

### D17 — Email verification without SMTP probing
- **Decision.** Verify via syntax + MX/domain-liveness + role/pattern heuristics; no SMTP RCPT probing. Unverifiable emails are honest `could_not_verify` blanks.
- **Reasoning.** SMTP probing from free/cloud IPs is unreliable (greylisting, catch-all) and treated as abusive/blacklistable (gate-review A8). A guessed "verified" value is disqualifying; an honest blank is candour.
- **Alternatives considered.** SMTP RCPT probing (rejected: unreliable + abusive); paid verification API (rejected: free-tier constraint).
- **Tradeoffs.** Fewer "deliverable"-labelled emails, but every label is defensible under sampling.
- **Risks.** Lower contactable-email fill rate → compensated by entity-level intelligence (thesis, AUM, signals).
- **Future improvements.** A defended, budgeted paid verification pass if the role permits.

### D18 — Source-diversity selection policy for the shipped file
- **Decision.** `select_final()` caps any single discovery source at ~40% of the delivered N; relax only with a logged justification. Wikipedia/Wikidata are discovery-only and blocked as verification (gate G5).
- **Reasoning.** The pool is 62% SEC; the anti-"copy at scale" rule applies to what we ship (gate-review A10). Community-edited references are not authoritative verification.
- **Alternatives considered.** Ship the pool distribution (rejected: SEC-dominated); hard cap with no relaxation (rejected: could fail to reach 50).
- **Tradeoffs.** May include slightly lower-ranked non-SEC records to balance, for defensible diversity.
- **Risks.** If non-SEC qualifying supply is too thin, the cap relaxes (logged) → mitigation is to strengthen non-SEC discovery.
- **Future improvements.** More non-SEC lenses (state registries, curated MFO lists).

### D19 — Postgres/Supabase backend implemented behind the interface
- **Decision.** Real `SupabaseRepository` (psycopg, jsonb) mirroring SQLite; selected when `DATABASE_URL` is set; psycopg imported lazily so a missing driver gives a clear error, not a dangling import.
- **Reasoning.** D5 claimed "Postgres from the beginning" but only SQLite existed and the factory had a dangling import (gate-review A6). The claim must match reality.
- **Alternatives considered.** SQLite-only + reworded docs (rejected: weaker deploy story); a NotImplementedError stub (rejected: placeholder, forbidden).
- **Tradeoffs.** A second backend to maintain; validated against a live instance only at deploy (roundtrip test skipped without `TEST_DATABASE_URL`).
- **Risks.** Untested-in-CI-here → the error path is always-tested and the SQL mirrors the tested SQLite backend.
- **Future improvements.** pgvector for the semantic index at scale.
