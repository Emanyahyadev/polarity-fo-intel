# Stage 2 Build Session Summary

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
