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

### D2 — Discovery from four lenses: SEC EDGAR · IRS 990-PF · Wikipedia/Wikidata · GDELT
- **Decision.** Four lenses — regulatory (SEC EDGAR full-text search over 13F/SC filings; **not** IARD Form ADV), tax-exempt (IRS 990-PF via ProPublica), curated (Wikipedia `Category:Family_offices` + Wikidata `Q751314`, discovery-only), media (GDELT, **signals-primary** — its generic query proved weak for bulk discovery). Discovery kept separate from proof sources.
- **Reasoning.** One convenient source = automatic fail. Independent lenses give genuine market discovery; 990-PF surfaces families behind foundations; the curated lens finds notable (heavily single-family) offices; GDELT supplies per-firm dated signals. Empirically, news yields ~0 bulk discovery, so the *shipped* file is discovered by three active lenses — reconciled honestly in Architecture §4 and BuildLog Session 3.
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

### D4 — Repository visibility (amended: now public)
- **Decision (original).** Private GitHub repo shared with optimize@falconscaling.com; raw scraped payloads gitignored.
- **Amendment (2026-07-28).** The repository is now **public**. Making it private broke the free-tier host's repository access (its GitHub connection could not read a private repo without a re-authorization), blocking deploys of the live URL. Public is acceptable on review of what the repo actually contains: every delivered datum is sourced from **public regulatory filings** (SEC EDGAR 13F, SEC IAPD / Form ADV) and **public firm websites** — the dataset aggregates already-public information, and unverifiable personal contact fields (emails, LinkedIn, direct lines) were never populated. The working candidate database and raw scraped payloads remain gitignored and were never committed (verified against the full git object history).
- **Reasoning.** The assessment allows "public **or** shared"; a working live URL is a hard deliverable, and deploy continuity outweighs the marginal privacy benefit of gating data that is public at its source.
- **Tradeoffs.** The aggregation of public contact data is more discoverable in a public repo; accepted because each datum is individually public and honestly sourced.
- **Risks.** None material beyond the accepted tradeoff.
- **Future improvements.** A scrubbed portfolio fork is no longer necessary; if the dataset ever ingests non-public or licensed data, revert to private + shared access.

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

### D13 — Deployment target: Render free web service (revised from HF Spaces)
- **Status (live, verified).** Deployed at **https://family-office-intelligence.onrender.com** from this repo via `render.yaml` (Blueprint). `/health` → `{"status":"ok","records":60}`; on-/off-topic query transcript in `docs/evidence/live-url-query-transcript.md`.
- **Revision.** HF now gates *both* Docker **and** Gradio Spaces behind PRO — only Static Spaces are free (two separate live 402s confirmed this: one on a Docker Space, one on a Gradio Space during this build). Vercel/Netlify serverless size + duration limits do not fit the onnxruntime embedding model + in-memory index; shared hosting (Hostinger) cannot run a long-lived ASGI process with a native ML dependency. **Render** (free Docker web service) runs the existing `Dockerfile` unchanged and required no code compromise.
- **Decision (original).** Deploy the FastAPI + UI as a Docker container.
- **Reasoning.** Free public URL, supports local embeddings, no architecture change from the committed image.
- **Alternatives considered.** HF Docker/Gradio Space (both now PRO); Vercel/Netlify (serverless limits vs onnxruntime); Fly.io/Railway/Cloud Run (require a credit card); Hostinger shared hosting (no persistent ASGI process / native deps).
- **Tradeoffs.** Render free services sleep after ~15 min idle (cold start ~30–60 s) → mitigated by a scheduled `keepalive.yml` GitHub Action pinging `/health` every 10 min so the demo stays warm through the review window.
- **Risks.** onnxruntime image size → the Dockerfile uses fastembed (ONNX, no torch) and pre-warms the model at build, keeping the image within Render's free build limits (build succeeded).
- **Future improvements.** Custom domain (e.g. CNAME a Hostinger subdomain onto the service); external uptime monitor as a second keep-warm.

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
- **Decision.** Content-address retrieved sources (sha256) with `fetched_at` in each cell's provenance; write a run manifest (git commit, schema/pipeline version, timestamps, counts) per run; bundle the snapshots backing the released 55 into `docs/evidence/` at export.
- **Reasoning.** Live sources drift; without retained content a claim cannot be reproduced months later (gate-review A3).
- **Alternatives considered.** URLs only (rejected: rot/drift); committing all raw content (rejected: bulky, PII, third-party).
- **Tradeoffs.** Snapshot storage + a small export-time bundle step, for genuine reproducibility of the delivered records.
- **Risks.** Working snapshots are gitignored → the committed repo is self-contained only for the bundled released 55 (documented in KnownLimitations).
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

---

*Decisions D20–D22 were added when deepening commercial intelligence (principal / AUM / thesis / signals).*

### D20 — SEC Form 13F as the deep-intelligence source (principal, AUM, recent investments)
- **Decision.** For firms that file 13F, extract from the filing itself: the signatory's **name + title + phone** (principal), the summary page's **aggregate 13(f) securities value** (AUM), and **new positions vs the prior quarter** (recent investments). Gated on **freshness (≤ ~25 months)** — a stale filing contributes nothing. Website-stated AUM is **not used**.
- **Reasoning.** The IAPD API exposes registration but not Item 5 (AUM) or Schedule A (owners); the 13F filing exposes real, dated, content-hashable principal/AUM/holdings for free. A stale filing's signatory may have left and its value be out of date; a scraped website AUM proved unreliable (e.g. a bogus "$35B" industry figure). Trust > coverage.
- **Alternatives considered.** ADV Part 2 PDF parse for AUM/owners (rejected: heavy, unreliable); the IAPD individuals endpoint (rejected: 195 associated persons, no clear principal); website AUM (rejected: mis-parses); pattern-guessed emails (rejected: not verifiable → `could_not_verify`).
- **Tradeoffs.** Depth is bounded to ~25 of the delivered records (the 13F filers); the principal is the *signatory* (often CCO/GC), disclosed as such in `reviewer_notes`. Non-13F firms keep honest `could_not_verify`.
- **Future improvements.** ADV Part 2 structured data for total AUM + Schedule A owners; principal role disambiguation (lead investor vs signer).

### D21 — Post-enrichment entity resolution (dedup on shared domain / geography)
- **Decision.** After enrichment, merge records that share a website **domain** or exact **name + state + country**, keeping the richer record. Conservative: same name + different geography stays distinct (D14).
- **Reasoning.** The candidate-stage resolver runs before enrichment, so a firm found via two lenses (SEC 13F CIK + IAPD CRD) can survive as two records until enrichment reveals the shared domain — which is exactly how a Marcuard duplicate reached the delivered 55. Fix the class of defect, not the row.
- **Alternatives considered.** Manual row edit (rejected: not reproducible, the user explicitly required a pipeline fix); fuzzy auto-merge (rejected: D14 over-merge risk).
- **Tradeoffs.** A second resolution pass; deterministic and logged.

### D26 — SFO expansion: two website-verified single-family offices (MSD Capital, Willett Advisors)
- **Decision.** Add **MSD Capital, L.P.** (Dell) and **Willett Advisors LLC** (Bloomberg), each verified against the firm's **own website** with an explicit single-family quote ("exclusively manages the assets of Michael S. Dell and his family"; "manages the philanthropic assets of Michael R. Bloomberg"). Seven notable candidates were tested through the same gate; **five were rejected** — Bezos Expeditions, Ballmer Group and Mousse Partners because their sites do not self-identify as family offices, Declaration Partners and Pontegadea because no official site content could be verified, and Athos (Strüngmann) earlier because no official site exists. Delivered set: 55 → **57**; SFO 4 → **6**. **Batch 2 (same gate, 2026-07-29):** 25 further candidates tested; **three added** — Cherng Family Trust ("the multi-generational family office and investment firm of Andrew and Peggy Cherng"), Blue Haven Initiative ("We are a family office…", founders named on-site), and Artémis ("Artémis is the investment company of the Pinault family" — accepted on human review after the automated judge, running on a fallback model, missed the verbatim opening line; construction identical to the accepted Korys evidence; the overrule is recorded in the record's reviewer note). **22 rejected**, including Gates Ventures, Emerson Collective, Lawrence Investments, The Pritzker Organization, JAB, Grosvenor, Bregal and Anthos (no on-site single-family self-identification), Dentressangle (family named only via the brand — inference is not evidence), and several sites that could not be scraped. Delivered set: 57 → **60**; SFO 6 → **9**. (scripts/verify_sfo_batch2.py, scripts/add_sfo_batch2.py.) The family served is deliberately **not** recorded as `principal_name` (Dell/Bloomberg are the clients of the office, not its named decision-makers; the sites name no office head), and AUM/contact fields stay `could_not_verify`. (`scripts/verify_sfo_targets.py`, `scripts/add_sfo_records.py`.)
- **Reasoning.** SFO weight is the dataset's commercially weakest number, and these are the exact private offices the SEC-signal pipeline structurally misses (both are firm-type gold-set territory). Their own websites provide affirmative Rule-2 evidence at the same standard as the existing four (D24/D25). MSD is ingested under the site's own name (Wikipedia lists it under the later corporate name DFO Management) — the identity guard that correctly blocked the mismatched name earlier passes the site's own name.
- **Alternatives considered.** Including Bezos/Ballmer/Mousse on their notability (rejected: no on-site self-identification = no affirmative evidence); citing press/Wikipedia as verification (rejected: G5, discovery-only); skipping the expansion entirely (rejected: two marquee, fully-verified SFOs materially improve the dataset's stated weakness).
- **Tradeoffs.** Single verification source (own site) → Medium confidence, honestly labelled; no AUM/principal depth for either (no free authoritative source).
- **Risks.** A site could overstate its nature → mitigated by requiring an exact self-identification quote naming one family, and by the audit trail of the five rejections.
- **Future improvements.** Re-test the rejected five if their sites change; SEC 13D/13G cross-references where these offices file on US positions.

### D25 — Consistent SFO/MFO classification via the SEC Family Office Rule
- **Decision.** Apply ONE uniform, evidence-first rule to every record (`scripts/apply_classification.py`): (1) explicit single-family website statement → **SFO**; (2) explicit multiple-families/clients website quote, plural-verified → **MFO**; (3) SEC Form ADV **Item 5.F regulatory (client) AUM** reported → **MFO**; (4) **ACTIVE** SEC adviser registration by **exact CRD match** → **MFO** — under the SEC Family Office Rule (17 CFR 275.202(a)(11)(G)-1) a bona-fide single-family office is *excluded* from adviser registration, so an actively-registered "family office" adviser necessarily serves clients beyond one family; (5) otherwise (inactive/withdrawn registration, or status not verifiable by an exact identifier) → **Undetermined**. MFO (the conservative label) may be asserted from an authoritative regulatory fact; SFO only from an explicit single-family statement. Result: **4 SFO / 37 MFO / 14 Undetermined**; every `fo_type` carries clean evidence (0 rows saying "not established"); every change is audit-logged.
- **Reasoning.** The review board found (a) 9 MFOs whose evidence literally still said "single vs multi not established," and (b) an inconsistency — Geller ($5.01B Item-5.F client AUM) was Undetermined while WE/JFG were MFO on that exact signal, with ~22 registered advisers stuck in Undetermined. Registration status *is* an authoritative classification signal: the Family Office Rule makes an active registration dispositive that a firm is not a bona-fide SFO — stronger and more consistent than a marketing phrase.
- **Alternatives considered.** Keep the website-quote-only rule (rejected: leaves the contradiction + 55% Undetermined + the Geller inconsistency); promote inactive/withdrawn firms to SFO on the exemption logic (rejected: withdrawal can also mean closure — asserting SFO is the dangerous direction; kept **asymmetric** — active ⇒ MFO, but SFO needs an explicit statement); trust name-based IAPD matches for 13F-only firms (rejected: name collisions, e.g. "Duquesne"/"Louis-Dreyfus" — the exact failure behind the earlier contamination).
- **Tradeoffs.** MFO rises to 37 of the delivered records (registration-inferred ones carry Medium confidence with a transparent Family-Office-Rule evidence string a reviewer can audit); genuine-but-unregistered SFOs that file 13F (Duquesne, Louis-Dreyfus) stay Undetermined because their registration status can't be confirmed by an exact identifier — honest under-classification over a name-collision risk.
- **Risks.** A registered adviser could be near-single-family yet labelled MFO on registration → mitigated by Medium confidence + the transparent, auditable evidence.
- **Future improvements.** Resolve exact CRDs for distinctively-named 13F-only firms to classify them without collision risk; ADV Part-2 client-count data to confirm multi-family directly.

### D24 — Discovery diversity: non-SEC family offices verified via their own websites
- **Decision.** Add 5 Wikipedia/Wikidata-discovered (non-SEC) family offices — Financière Agache (Arnault), KIRKBI (LEGO / Kirk Kristiansen family), Korys (Colruyt family), Builders Vision (Lukas Walton), and Prime Opportunities — each verified against the firm's **own authoritative website** (Firecrawl scrape + strict extraction that requires an exact on-site self-identification quote **and** a firm-identity match). Discovery source = Curated directory (non-SEC); verification = firm website. **Skipped** DFO Management (its site presents as "MSD Capital" — a name mismatch), Bezos Expeditions / Walton Enterprises / Mousse Partners (no public site to verify), and the Rahul Guhathakurta HUF (a "passive non-operating" personal Hindu-Undivided-Family entity — not an institutional family office). Also wired **country filtering** into the RAG and made a hard metadata-filter match **authoritative** for in-domain queries (`scripts/verify_directory.py`, `scripts/build_directory_records.py`).
- **Reasoning.** The delivered set was 96% SEC-discovered — the biggest risk against the "provably multi-source / single-source-at-scale = auto-fail" rule. These marquee SFOs are exactly the private family offices the SEC-signal classifier structurally misses (they are firm-type gold-set false negatives); their own websites are authoritative Rule-2 evidence, while Wikipedia/Wikidata stay discovery-only (gate G5). Result: non-SEC discovery 2→7, SFO 12→4 (only genuine single families kept), international 4→7 countries, SEC discovery share 96%→87%, N=50→55. (The MFO/Undetermined split was subsequently made consistent in D25.)
- **Alternatives considered.** Add SEC-discoverable 13D/13G filers (rejected: does not improve *discovery* diversity); include Bezos/Walton with no verifiable site (rejected: would fabricate); include the HUF (rejected: not decision-grade); trust Wikipedia as verification (rejected: G5).
- **Tradeoffs.** These records rest on a single verification source (the firm's own website), so they carry Medium/Low confidence, honestly labelled; family-controlled firms (Kirkbi, Korys) get a blank principal (could_not_verify) rather than a family name forced into a person field.
- **Risks.** A firm could overstate its family-office status on its own site → mitigated by requiring an exact on-site quote + firm-identity match, and by conservative confidence. **Mitigation for the RAG shortcut:** the authoritative-filter answer fires only when the query also carries a family-office domain term, so a state/country name in an off-topic query ("best pizza in Texas") still abstains (regression-tested).
- **Future improvements.** Add a second authoritative source per firm (national company registries; the firm's SEC 13D/13G where it files) to lift confidence from Medium toward High.

### D23 — Generic-name website guard + registration-status verification (contamination correction)
- **Decision.** A firm whose name has **no distinctive token** (generic core, e.g. "The Family Office, LLC") may **not** be matched to a website — a generic name cannot confirm the site is the firm's. On re-verification, `THE FAMILY OFFICE, LLC` (CRD 288530) had an unrelated company's site (`thefamilyoffice.com`, a residential real-estate advisory) attached through its generic name; every website-derived field (website/description/thesis/principal/type) was **removed** and the record reset to only IAPD-authoritative facts. Separately, each IAPD-mapped firm's live **registration status** was re-checked against the SEC IAPD firm API: the **5 inactive/withdrawn** firms are kept only where independent operating evidence exists (verified website / recent 13F / ADV AUM) and each carries an explicit status note.
- **Reasoning.** A generic name is the exact failure mode that lets a wrong site through the name-match guard, and it silently poisons the highest-value fields. Withdrawn SEC registration is common and often *expected* for a genuine family office (SFOs are excluded under the SEC Family Office Rule), so it is disclosed, not treated as disqualifying — but it must never be presented as active. Both are "fix the class of defect, then the row" (per the user's quality-first mandate).
- **Alternatives considered.** Manual spreadsheet edit (rejected: not reproducible — done as `scripts/correct_contamination.py`); dropping the record to 49 (rejected: the assessment requires 50+, and the entity is genuinely IAPD-registered); dropping all 5 inactive firms (rejected: 4 have independent proof of operation and inactivity is expected for family offices).
- **Tradeoffs.** One record collapses to a thin IAPD-only record (Low confidence, honestly flagged); the generic-name guard will skip enrichment for any future generic-named firm rather than risk a wrong match.
- **Risks.** A firm with a genuinely generic name and a correct generic domain is under-enriched → acceptable (silence over a wrong value). **Mitigation:** such firms keep their authoritative registration facts.
- **Future improvements.** Match generic-named firms to a website only via an authoritative cross-reference (the firm's own ADV Item 1.I website field) rather than name/search heuristics.

### D22 — Precompute embeddings + slim serving image (fit the 512 MB free instance)
- **Decision.** Build a **serving-only** requirements file (no pandas/lxml/pytest/etc.) and **precompute the 60 document vectors at image-build time**; the runtime loads vectors instead of running the ONNX model at startup. The model then loads lazily on the first query.
- **Reasoning.** The full requirements OOM/timed-out the free build; and loading onnxruntime + the model *while* embedding all delivered docs at startup exceeded 512 MB ("used over 512Mi" in the logs) and killed the container. Precomputing removes the startup spike; the lean image builds fast and reliably. Verified on a live deploy (health + abstention + deep-data queries).
- **Alternatives considered.** Swap to model2vec/static embeddings (deferred: larger change + re-tune + re-eval); a paid instance (rejected: strictly free-tier); hosted embedding API (rejected: adds a key, D1).
- **Tradeoffs.** The vectors are a build artifact (gitignored, regenerated from the committed CSV); a stale artifact is guarded by a shape check + build-time regeneration.
