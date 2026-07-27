# Build Session Summary

> **Candidate: please set the actual working-time figures below to your real hours (do not pad — inflated hours are a negative signal) and confirm this reflects your framing before submission.**

**Approximate build time:** ~__ hours of focused work across the window *(candidate to fill in actual time)*.

**Main work sessions**
1. **Analysis + architecture** — read the brief and *How We Work* line-by-line; designed the layered pipeline (discovery → enrichment → validation → gate → store → RAG → serve); wrote the data model with the two rules of proof.
2. **Discovery** — built four discovery lenses; tested every source API against reality before coding; caught the Google-News-RSS ToS issue and repositioned news to signals.
3. **Architecture Gate Review + remediation** — deliberately paused, reviewed the repo adversarially against the brief, and hardened it: evidence-based entity resolution, the release gate as the single publication authority, provenance enforcement, reproducible run manifests, the Postgres backend, honest documentation.
4. **Enrichment + validation + dataset** — SEC submissions, SEC Form ADV/IAPD (the lens that unlocked scale), constructed-domain website verification; firm-type classification against a written inclusion standard; produced the validated 50 + a gold-set evaluation.
5. **Micro-RAG + deploy** — hybrid retrieval, code-enforced grounding/abstention, a non-technical UI, containerised for a free-tier public URL.

**Tooling and what I decided on top of it.** AI coding tools were used throughout — that is expected for this role. The tools generated code, connectors, and first-draft prose fast; the **judgment is mine and is where the value is**:
- The **inclusion standard** (what qualifies as a family office, what evidence is required) — a human policy the pipeline enforces.
- The **precision-over-recall decision**: reject rather than guess. The gold set proves a **0% false-positive rate** at the cost of recall — I chose that tradeoff because shipping a fake family office costs a client's trust, while missing one costs a lead.
- The **honest scarcity finding**: rather than manufacture source diversity to hit a number, I widened discovery, *measured* that the free-tier verifiable universe is finite, and documented it quantitatively.
- **What I refused to ship**: SMTP email-probing (unreliable + abusive), Wikipedia-as-verification, guessed values dressed as verified, and any record that failed a gate.
- Every AI output was checked against reality — APIs probed live, records spot-checked, claims reconciled with artifacts, a gate review run to find my own weaknesses before a reviewer would.

**Known limitations I am not hiding:** records are firm-level (not yet principal-level); discovery is SEC-heavy though every record is multi-source *verified*; some types are honestly Undetermined; the RAG dataset is intentionally small and validated. All are documented in `KnownLimitations.md`.
