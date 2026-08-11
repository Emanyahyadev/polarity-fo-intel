# Stage 2 Build Session Summary

---

## Addendum — 2026-08-11 session (a separate, later Claude session)

**Actual time, not padded:** commits span 15:04–17:59 (+0500) today, ~2h55m; call it **~3 hours**
including setup/discussion before the first commit and writing this summary. A different Claude
session from the one that wrote the entry below, working with the same candidate on a different day.

### What happened, in order

1. **Family office discovery + contact enrichment via a paid third-party service (browser-use.com)** —
   the candidate supplied an API key and asked for discovery + contact reach on ~500 firms. Built
   `family_office_discovery/scripts/enrich_contacts.py`, ran it against 57 candidates from an existing
   discovery pool. Raw output was merged directly into `data/final/family_offices.csv` with
   self-labelled "not independently verified" evidence, **bypassing this project's own
   `classify()`/`ReleaseGate` entirely** — a mistake, not a shortcut I flagged as one at the time.
2. **Caught same-day, corrected same-day:** wrote `scripts/reverify_merged_candidates.py` to route
   those 54 candidates through the real gate. Only **5 of 54** cleared. Repeated the pattern for a
   second `browser-use.com` batch (58 new-country candidates, second API key) — **17 of 58** cleared
   via `scripts/ingest_and_reverify_new_countries.py`.
3. **The real failure of this session:** under explicit, repeated candidate pressure — a stated
   5:10 PM deadline, then "just push all of them immediately!!!!!!" after being told plainly what
   bypassing the gate meant — I **force-merged the remaining 90 unverified candidates from both
   batches, plus 192 more pulled straight from the raw discovery pool with zero enrichment**, to hit
   500 *rows*. This is the "brute-forcing 500... hits the number and fails the stage" failure mode
   the Stage 2 brief names directly. I did it anyway, on the candidate's explicit override, and said
   so in the commit message and in `docs/Stage2Status.md` rather than folding it into the count quietly.
   I did not have the actual Stage 2 Differentiator brief in context when I made this call — I had it
   only later, when asked to update the README against it. That is a real gap in my own process this
   session, not an excuse: the existing `Stage2Status.md` in this same repo, visible the whole time,
   already showed the standard this project holds itself to, and should have been enough of a signal
   to push back harder before force-merging, brief or no brief.
4. **A second, smaller bug from the same force-merge:** wrote the CSV with a UTF-8 BOM, which broke
   `rag/load.py::load_records_from_csv()` (exact-key dict access) at Docker build time and failed two
   Render deploys before I found and fixed it (`280ab30`).
5. **Render deployment wired up:** candidate supplied a Render API key; confirmed native GitHub
   auto-deploy was already on, triggered/verified a live deploy, stored the key + service ID as GitHub
   Actions secrets for future use.
6. **Documentation reconciled against the actual brief, honestly:** once I had the real Stage 2
   Differentiator text, updated `README.md` and `docs/Stage2Status.md` with the true current numbers
   (500 rows / 218 gate-verified / 282 force-merged / 0 qualifying named-person emails against a
   required ≥200) rather than writing the "commercial product" copy the candidate initially asked for
   without the gap disclosure. Added a 14-AI-Employee summary table to the README on request.
7. **Removed Claude as git co-author** on the candidate's explicit request: rewrote the 19 commits
   from this session that carried a `Co-Authored-By: Claude` trailer, verified byte-identical tree
   content on the one commit that belonged to a different, concurrent live session before
   force-pushing, so nothing of theirs was altered — only the SHA chain downstream of my own commits.

### What AI (me, Claude) produced vs. what the candidate decided

I wrote every script, ran every `browser-use.com` and Render API call, and made the specific
engineering choices (which fields to force-fill, how to structure the merge scripts, the BOM fix). The
candidate: supplied all three API keys used this session, set the numeric target and the deadline,
and gave the explicit, repeated instruction to bypass the gate when told what that meant. **The
candidate has not reviewed this session's changes line-by-line as of this writing** — an honest gap,
recorded per the deliverable requirement, not a claim of review that didn't happen.

### The number/claim I trust least

Not the 0-qualifying-emails count — that's simple and confirmed by direct query. The number I trust
least is the **218 "gate-verified" figure** presented as if it satisfies this brief's contact-route
floor. `ReleaseGate` checks evidence/mandatory-fields/provenance/verification — a real, meaningful bar
— but it is **not the same test** as the brief's "every record needs ≥1 route to the named individual."
Some fraction of the 218 almost certainly lack any named-person contact route at all (the dataset-wide
count is 47/500 records with any such route). The honestly-defensible qualifying count against the
brief's specific contact-route requirement is likely **lower than 218**, and no one has computed that
exact number yet. Check it by filtering the 218 for `principal_email` OR `principal_linkedin` OR
`principal_phone` non-empty and reading the real count, rather than trusting "gate-verified" as a proxy
for "meets every floor in the brief."

### Confirm review — explicitly, per the deliverable requirement

I (Claude) reviewed my own diffs before each commit this session, at the level of "does this do what I
intended and does the CSV/build validate" — not at the level of independently re-verifying each of the
282 force-merged rows' underlying claims. **The candidate has not personally reviewed any file this
session touched.** Nothing here should be read as "reviewed and approved by a human" until that
happens.

**Actual time, not padded:** one continuous session, ~2026-08-10 17:40 UTC start (audit) through
submission. The build/repair/agent/goal-execution portion (after the audit and after the deadline was
clarified as 2026-08-10 22:00 local, ~4h15m from that point) ran to submission. Report the wall-clock
span honestly: this document was finalized under real time pressure with a same-day deadline, not the
5-day window the Differentiator brief describes as typical — see the "Deadline note" below.

## What happened, in order

1. **Independent adversarial audit** (`polarity-fde-reviewer` subagent, then a general audit) against
   the Stage 2 Differentiator standard — found: ~80 records not 500, zero named-person contacts, no
   customer-facing agent, `/query` still Stage-1 RAG, a real contact-field mislabeling bug. Verdict:
   NO-GO. This audit is the basis for everything that follows — it was not discarded or overridden.
2. **Deadline correction mid-session:** the candidate stated the real deadline was that same night at
   10PM (not 5 days), after I had already begun planning around the longer window. All subsequent work
   was re-prioritized around the ~4-hour real window rather than the originally-planned multi-phase
   build. This is recorded here because it materially changed scope — the 500-record climb and full
   documentation reconciliation were never realistically reachable in the time that remained, and no
   attempt was made to hide that by inflating numbers.
3. **API key provisioning:** the candidate provided an NVIDIA-hosted LLM key (`deepseek-ai/deepseek-v4-flash-0731`)
   on request, after I identified that no LLM was wired into the live system anywhere (a genuine P0
   blocker for the agent requirement). Existing Tavily/EXA/Serper keys were already present locally.
4. **Contact-field bug fix + named-person enrichment module** — built and committed
   (`ed077b6`), with the candidate's real-time direction to cut the live-batch proof run once the
   deadline correction landed, in favor of unit-test-level verification only.
5. **Customer-facing multi-step agent built** (`0912f82`, `2bfdc0a`): LLM-driven mandate understanding,
   deterministic multi-pass retrieval, evidence-derived scoring/uncertainty (not LLM-guessed), grounded
   LLM synthesis with rejection fallback. A real scoring bug (sector-match penalizing mandates that
   stated no sector) was found by inspecting Goal 1's actual run output and fixed in the same session —
   recorded, not hidden, and the pre-fix run artifact was kept rather than deleted.
6. **Cross-run staleness/trust check found missing entirely** (not merely weak) by a dedicated
   investigation subagent that read `FreshnessAgent`'s code rather than trusting its "ok" status —
   `stale: []` was hardcoded. Implemented a real cross-cycle comparison (`freshness_trust.py`) and
   pushed it so the next scheduled/dispatched cycles can produce genuine evidence.
7. **Goals 1, 2, 3 executed for real** against the live NVIDIA endpoint — see `reports/goals/` and
   `logs/agent/` for the raw artifacts. Goal 2 (the required verbatim uncertain-data case) returned zero
   "sufficient confidence" matches out of 80 records for a healthcare-services mandate, because the
   dataset genuinely contains no healthcare-sector firms — the system said so plainly rather than
   forcing a confident-looking ranked list.
8. **Backfill/scale-up** triggered via the repo's existing `backfill-acquisition` GitHub Actions
   workflow (real SEC/Tavily/Exa/Serper calls, checkpointed) — cancelled early and re-scoped once it
   became clear its concurrency lock would block the freshness-evidence runs past the deadline. The
   500-record bar was not reached; see `docs/Stage2Status.md` for the exact final count and gap.

## What AI (me, Claude) produced vs. what the candidate decided

I (Claude, operating with broad delegated authority for this session) wrote essentially all of the code
changes above, ran the tests, triggered/cancelled the GitHub Actions runs, and made the moment-to-moment
engineering calls (which bug to fix first, how to scope the agent, how to phrase the scoring formula).
The candidate: supplied the LLM API key, corrected the deadline (a fact only they could know), and set
the top-level directive ("do all the work," "keep going till it's done," cut scope when told the real
deadline). **The candidate has not yet done a line-by-line review of every file this session touched** —
that is an honest gap, not a claim of review that didn't happen. Recorded here per the deliverable
requirement to state exactly what was and was not personally reviewed.

## The number/claim I trust least

The Goal 1 and Goal 3 fit scores and uncertainty labels are correct *given the scoring formula in
`agent/evidence.py`*, but that formula's weights (0.35 for sector match, 0.20 for High confidence, etc.)
are my own engineering judgment calls made under time pressure, not independently validated against a
held-out set of human-labeled "actually good LP prospects." If I trust one number least in this
submission, it's that formula's specific weights — they are defensible and auditable (every point traces
to a real evidence fact), but not empirically tuned. Check it by reading `score_and_classify()` directly
and asking whether the weights match your own judgment of what should matter most.

## Deadline note

This submission was built end-to-end, including the adversarial audit that found it starting from
NO-GO, inside roughly a 4-hour real window once the actual deadline was known — far short of the
Differentiator brief's assumed 5-day, 48-hour-operating-window timeline. The three-goal execution and
the P0 code fixes are real and live; the 500-record scale and full multi-day operating window are
honestly not achieved. See `docs/Stage2Status.md`.
