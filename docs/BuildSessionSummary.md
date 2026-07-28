# Build Session Summary

> **Candidate: please set the actual working-time figures below to your real hours (do not pad — inflated hours are a negative signal) and confirm this reflects your framing before submission.**

**Approximate build time:** ~__ hours of focused work across the window *(candidate to fill in actual time)*.

**Main work sessions**
1. **Analysis + architecture** — read the brief and *How We Work* line-by-line; designed the layered pipeline (discovery → enrichment → validation → gate → store → RAG → serve); wrote the data model with the two rules of proof.
2. **Discovery** — built four discovery lenses; tested every source API against reality before coding; caught the Google-News-RSS ToS issue and repositioned news to signals.
3. **Architecture Gate Review + remediation** — deliberately paused, reviewed the repo adversarially against the brief, and hardened it: evidence-based entity resolution, the release gate as the single publication authority, provenance enforcement, reproducible run manifests, the Postgres backend, honest documentation.
4. **Enrichment + validation + dataset** — SEC submissions, SEC Form ADV/IAPD (the lens that unlocked scale), constructed-domain website verification; firm-type classification against a written inclusion standard; produced the validated 50 + a gold-set evaluation.
5. **Micro-RAG + deploy** — hybrid retrieval (semantic + BM25 + metadata incl. a numeric AUM filter), code-enforced grounding/abstention, a non-technical UI, containerised for a free-tier public URL.
6. **Deep commercial intelligence** — SEC Form 13F parsing for principal (signatory) + AUM (13(f) value) + recent investments; firm websites for investment thesis; SEC bulk Form ADV (Item 5.F total AUM + Schedule A owner-principal) for registered non-13F firms; post-enrichment entity resolution that fixed a delivered duplicate through the pipeline (not by hand).
7. **Adversarial hardening + live deploy** — caught and fixed, on my own review or the user's testing: top-k answer padding, an abstention hole (domain-word queries), unreliable website AUM (a bogus "$35B"), stale-filing principal/AUM, a 512 MB OOM at container startup (precompute embeddings at build), and free-tier host churn (HF→Render). Verified the live URL end-to-end.

**Tooling and what I decided on top of it.** AI coding tools were used throughout — that is expected for this role. The tools generated code, connectors, and first-draft prose fast; the **judgment is mine and is where the value is**:
- The **inclusion standard** (what qualifies as a family office, what evidence is required) — a human policy the pipeline enforces.
- The **precision-over-recall decision**: reject rather than guess. The gold set proves a **0% false-positive rate** at the cost of recall — I chose that tradeoff because shipping a fake family office costs a client's trust, while missing one costs a lead.
- The **honest scarcity finding**: rather than manufacture source diversity to hit a number, I widened discovery, *measured* that the free-tier verifiable universe is finite, and documented it quantitatively.
- The **freshness + source-trust rules on deep data**: use 13F/ADV facts only from recent filings (a decade-old signatory has left; a scraped AUM can be an industry total) — fewer values, but every one authoritative and dated.
- **What I refused to ship**: SMTP email-probing, synthesised principal emails/LinkedIn (recorded as `could_not_verify`), Wikipedia-as-verification, website-scraped AUM, guessed values dressed as verified, and any record that failed a gate.
- Every AI output was checked against reality — APIs probed live, records spot-checked, claims reconciled with artifacts, a gate review + an adversarial pass run to find my own weaknesses before a reviewer would.

**Known limitations I am not hiding:** principal/AUM depth is bounded to firms that file 13F or an ADV (the principal is a signatory/control person, AUM is 13(f)- or ADV-basis — disclosed per record); discovery is SEC-heavy though every record is multi-source *verified*; some types are honestly Undetermined; contact fields free sources don't expose (LinkedIn, work email) are honest `could_not_verify`; the RAG dataset is intentionally small and validated. All are documented in `KnownLimitations.md`.
