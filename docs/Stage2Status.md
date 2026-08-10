# Stage 2 Status — stated plainly

This document exists because the Differentiator brief's own "Final Check Before You Submit" asks three
honesty questions directly. Answered here, truthfully, as of submission:

**1. Are most of the 500 records thin, generic, or blank?** N/A in the literal sense — there are not 500
records. The dataset holds **80 qualifying records** (unchanged from before this session's `firm_contact_email`/
`principal_email` field-split fix — see below), each of which passed the pre-existing inclusion standard
(`config/inclusion_standard.md`, Rule 1 + Rule 2, enforced in code, not by hand). Of those 80: 10 Single-Family
Office, 15 Multi-Family Office, 55 honestly labeled Undetermined (proven family offices whose SFO/MFO split
could not be established — a candor label, not padding). **The 500-record bar is not met. This alone fails the
stage's hard minimum per the brief's own text**, regardless of quality elsewhere.

**2. Does the file contain values labeled more strongly than the evidence supports?** As of this session: no
known instance, and one real one was actively fixed. Before this session, `principal_email` was populated
from a firm's *generic* published inbox (info@/contact@) with a "risky" status — technically labeled
correctly at the field-status level, but the field NAME itself implied a named-person route it wasn't. That
bug is fixed (`ed077b6`): the generic inbox now lives in `firm_contact_email`, and `principal_email` is
populated only when there is genuine name-matched evidence (currently zero records have this — the
enrichment code path is real but has not yet been re-run against live sites since the fix). Every
verified/confirmed/direct/principal/current claim surfaced by the agent (`src/fointel/agent/`) is
grounded and rejection-checked against the actual evidence bundle before it reaches the user — see
`agent/synth.py`.

**3. Would a first-time customer need the builder beside the screen?** Partially addressed, not fully solved.
The new Agent tab explains in plain language what it does, what it found, and why — but it has not been
user-tested with a real non-technical customer in this session, and the Directory/Research tabs still carry
some Stage-1-era language that has not been fully audited against the Product Language standard in this
window.

## Gate-by-gate, honestly

| Requirement | Status |
|---|---|
| 500 qualifying records | **Not met.** 80 on file. Real (not fabricated) scale-up was triggered via the existing `backfill-acquisition` GitHub Actions workflow but was time-boxed and does not reach 500 before submission. |
| ≥200 qualifying named-person emails | **Not met.** 0 on file. The generic-inbox mislabeling that would have made this number look better than it is has been fixed, not hidden. |
| Every record: ≥1 real route to the named individual | **Not met** for the great majority of records — most family offices in this dataset are privately held with no public staff directory (a structural source limitation, documented in `docs/AgentArchitecture.md` §1), not a pipeline defect. |
| Customer-facing agent, natural-language goals | **Real and live.** `POST /goal`, `src/fointel/agent/`. Two genuinely model-driven decision points (mandate understanding, grounded synthesis), deterministic evidence/scoring in between. See the three goal runs in `reports/goals/` and `logs/agent/`. |
| Goal 1 (self-framed multi-step search) | **Executed twice.** `reports/goals/goal-923b73bc7c.json` (local, pre-scoring-fix, kept as the historical artifact that surfaced the bug). Canonical: `reports/goals/goal-a20ad286ea-GOAL1-LIVE.json`, re-run against the LIVE deployed service post-fix — 32/80 records reach "sufficient" evidence, 7.2s end to end. |
| Goal 2 (verbatim uncertain-data case) | **Executed twice, consistent.** Local (NVIDIA): `reports/goals/goal-5017dab551.json`, 573s. Live (Groq): `reports/goals/goal-93f269059a-GOAL2-LIVE.json`, 5.0s. Both: 0/80 records reach "sufficient" evidence for a lower-middle-market healthcare-services mandate — genuinely correct, the dataset has zero healthcare-sector firms. The system said so both times; it did not force a confident ranking. |
| Goal 3 (buyer-challenge, contact-gap triage) | **Executed twice.** Live (Groq): `reports/goals/goal-99f7644650-GOAL3-LIVE.json`, 6.4s — correctly surfaces high-fit candidates with `contact_route: null` and a "worth manual research" recommendation, naming the specific decision-maker to research where known (e.g. Santiago Ulloa at WE Family Offices). Local (NVIDIA) run also executed for raw-trace diversity across two independent LLM providers — see `logs/agent/` for whichever run ID completed last locally. |
| Two genuinely separate scheduled operating runs, ≥48h apart, unattended | **Likely already satisfied** by pre-existing GitHub Actions history: `event:"schedule"` runs from 2026-08-08T09:09:33Z to 2026-08-10T11:00:05Z (>48h), confirmed via `gh run list`. Screenshots of the Actions run history and a single run's detail page still need to be captured by the candidate before submission — I cannot take screenshots. |
| At least one real dependency failure | **Satisfied, multiple ways.** Two schedule-triggered runs failed for real before this session: 2026-08-10T09:09:24Z and 2026-08-10T07:14:43Z (`gh run list --workflow=operating-cycle.yml`). During this session, manually triggered run `31395597811` (2026-08-10T13:57:54Z) genuinely failed end-to-end from a real bug this work introduced (a `git add` pathspec glob failure cascading into a rejected push) — not staged, not induced, found by watching the actual run fail and read in `gh run view --log-failed`; fixed in `c9b42db`. Separately, the local Goal 3 agent run hit a real LLM provider failure ("mandate LLM call failed", `logs/agent.log` 2026-08-10T14:04:24Z) and correctly degraded to the deterministic keyword fallback rather than crashing — see `agent/mandate.py`'s fallback path. |
| Cross-run, evidence-based staleness/trust event | **Mechanism built and proven to run correctly across two genuinely separate cycles; no real diff has fired yet, stated honestly.** Was completely unimplemented before this session (`FreshnessAgent` hardcoded `stale: []`). Fixed (`freshness_trust.py`, `2bfdc0a`), found and fixed two more real bugs that were silently breaking the commit step on every run (`c9b42db`, `8e5c5a1`) by watching actual runs fail. Two real, separate GitHub Actions runs then executed successfully: baseline `31397630141` (commit `87eda9a`, established `data/freshness/prior_snapshot.json`) and comparison `31398554032` (commit `b0b8768`, ~10 minutes later). The comparison found **zero trust-bearing field changes** — correct and expected, since nothing in the 80-record store actually changed in that ~10-minute window; an honest null result, not a failed check. **This table row cannot honestly be marked "satisfied" without a run that actually found a real diff.** A longer-running backfill cycle was triggered afterward specifically to increase the chance of a genuine field-level change (re-verification touching an existing record) surfacing before submission — check `gh run list --workflow=operating-cycle.yml` for any run after `31398554032` whose `cross_run_trust.stale` is non-empty before claiming this gate met. |

## Bottom line

The infrastructure fixes, the agent, and the three goal executions are real, live, and evidenced by
artifacts a reviewer can independently open. The 500-record scale and the named-person contact floor are
not met, and this document says so rather than dressing it up. Per the brief's own instruction: an
honestly incomplete submission is scored differently from a dressed-up one — this is the honest version.
