# Architecture Notes — Stage 2 Agent

Concise by design; every claim below corresponds to a file, a log line, or a table in this repo.

## 1 · Retrieval extension

New capability: `POST /goal` — a multi-step mandate agent (`src/fointel/agent/`) layered on top of
the existing single-call RAG (`src/fointel/rag/answer.py`, still served at `POST /query` unchanged).
The Stage 1 RAG could only answer one retrieval against the corpus per call and had no concept of a
customer *mandate*, ranking, or contactability. The agent can now: parse a free-text mandate into
structured criteria, run multiple retrieval passes (per stated sector, plus a full-dataset safety pass
so thin evidence is never silently dropped), score every candidate against the mandate on a fixed,
auditable formula, classify each candidate's evidence quality, and produce a ranked, cited,
uncertainty-labeled business output with a recommended next action — while never claiming a contact
route stronger than what governance (`PolicyEngine.contact_review`) already cleared.

Source classes and what each is strong enough to establish: SEC EDGAR 13F (authoritative principal
name/title/phone, dated AUM), SEC IAPD/ADV (registration status, regulatory AUM), firm websites
(self-described FO status/type, investment thesis, sectors, and — after the Phase 1 fix — named-person
contact only when a team/about page name-matches the principal), Tavily/EXA/Serper web search
(discovery only, never verification), IRS 990-PF and curated directories (discovery leads only, per
`config/inclusion_standard.md`). Material blind spot: many genuine SFOs are deliberately unlisted with
no public website, so website-based enrichment structurally cannot reach them — the dataset's SFO
count undercounts the true population for that reason, not from a pipeline defect.

Considered and rejected: giving the agent one large LLM call to "do everything" — rejected because it
would be exactly the "fixed pipeline with an LLM summary" the brief explicitly disqualifies, and
because it would put unenforceable trust language (confidence, verification) inside free-text
generation instead of in control flow.

## 2 · Agentic vs deterministic boundary

Genuinely agentic (the model decides): (a) `agent/mandate.py::understand_mandate` — turning free-text
into structured search criteria and flagging what's ambiguous or structurally unanswerable from this
dataset is open-ended NLU judgment a regex cannot defensibly make; (b) `agent/synth.py::explain_and_recommend`
— composing the plain-English "why" and the recommended action per candidate is open-ended language
generation. Both calls are grounded: the synthesis step is rejected and replaced with a deterministic
template per-candidate if the model's JSON doesn't parse, omits a candidate, or the fo_id isn't one it
was given (see `synth.py`'s grounding check, mirroring `rag/ground.py`'s existing pattern).

Deliberately kept deterministic: retrieval planning, evidence gathering, fit scoring, and uncertainty
classification (`agent/evidence.py`). Confidence and "how sure is the system" are the exact places a
wrong LLM guess is most damaging in family-office intelligence, so they are computed by a fixed,
inspectable formula from measured evidence (verification-source count, sector/geo match, freshness,
contactability) — never asked of the model. This mirrors the dataset's own existing rule that
field-level confidence is derived from provenance, never set independently
(`config/inclusion_standard.md`, `schema.py::field_confidence`).

## 3 · Authority boundary

The agent never grants itself new authority over the release dataset — it only reads
`data/final/records.json` (the same governance-approved store `/query` serves from) and only ever
displays a `principal_email`/`principal_linkedin`/`principal_phone` value if it already passed
`PolicyEngine.contact_review` during enrichment/release (Phase 1 wiring). It may decide freely: which
retrieval passes to run, how to score/rank, how to classify uncertainty. It must escalate/abstain: when
zero candidates clear even a thin-evidence bar for the mandate, the run emits an explicit `abstain`
trace event and the structured output says so rather than forcing a ranked list (see Goal 2's run — the
dataset has zero sector-matched candidates for "healthcare services," and the trace shows that
plainly). It must refuse: presenting a generic firm inbox (`firm_contact_email`) as a named-person
contact route — `evidence.py::_contact_route` structurally excludes that field from ever being offered
as a route, in code, not in a prompt.

## 4 · State, replay, and idempotency

Each goal run gets a `run_id` (`goal-<hex>`); its full JSONL trace is written to `logs/agent/<run_id>.jsonl`
and its structured output to `reports/goals/<run_id>.json` — both independently inspectable after the
fact, satisfying the "raw run log, not a narrated summary" requirement. A run is stateless/idempotent by
construction: it reads the released dataset fresh each time and writes only new, uniquely-named files;
re-running the same goal never mutates or corrupts a prior run's trace. The underlying data-refresh
cycle (14-employee LangGraph pipeline, unrelated to the goal agent) has its own checkpoint/resume
support in `operations/operate.py` / `data/backfill/checkpoint.json` — see the existing test suite
(`tests/test_checkpoint_interrupt.py`, `tests/test_backfill.py`).

## 5 · Cost and latency

Measured, not estimated, on two providers:

- **NVIDIA free tier (`deepseek-ai/deepseek-v4-flash-0731`, used for local development runs)**: a
  single grounded LLM call over the dataset took **377 seconds** in a direct measurement
  (`answer_query` against "What family offices are headquartered in Texas?"). A full goal run (2 LLM
  calls + local retrieval/scoring) took **573s (Goal 2), 270s (Goal 1, pre-fix)** end to end — see
  `logs/agent/goal-5017dab551.jsonl`, `logs/agent/goal-923b73bc7c.jsonl`.
- **Groq (`llama-3.3-70b-versatile`, the live Render deployment's actual configured provider)**: the
  SAME three goals, re-run against the live deployed service, completed in **5.0-7.2 seconds each**
  end to end (`reports/goals/goal-a20ad286ea-GOAL1-LIVE.json` 7.2s, `goal-93f269059a-GOAL2-LIVE.json`
  5.0s, `goal-99f7644650-GOAL3-LIVE.json` 6.4s) — roughly **50-100x faster** than the NVIDIA free tier
  for the identical code path. The manual single-call `/query` baseline is faster still (0.8-1.6s),
  which is the expected 2-LLM-call vs 0-or-1-LLM-call cost of genuine multi-step decomposition. All
  API cost is $0 on both providers' free tiers at this volume; the real constraint is the **shared
  Groq daily token quota** (100,000 tokens/day, already documented in `KnownLimitations.md` as shared
  with `/query`), not per-call price.

Retrieval/compute calls inside a goal run (multi-pass semantic retrieval, deterministic scoring over
all 80 records) are local and effectively free — no per-call API cost, since the corpus is embedded
once at startup and `ComputeEngine` runs in-process.

Refresh cost per record: dominated by web-search API calls (Tavily/Exa/Serper, all free-tier in this
build) and website fetches during enrichment, not by the LLM — the operating cycle itself makes zero
LLM calls (see `agents/contract.json`; no employee's `tools_used` includes an LLM). A precise $/record
figure requires a timed real batch cycle with paid-tier API pricing, which this session's free-tier
keys do not produce — stated as a gap rather than invented.

At 5,000 records, the first bottleneck is the free-tier LLM call latency and quota, not the dataset or
the deterministic pipeline: at ~130-380s per call, a customer-facing agent workflow that made even one
LLM call per record (it currently does not — it makes two calls per *goal run*, not per record) would
take over 24 minutes per 100 records serially. The actual near-term bottleneck for retrieval/query is
sentence-transformer embedding at startup (`rag/index.py`), which is O(n) in records and currently
recomputed synchronously on every deploy — at 5,000 records this becomes the first thing a customer
notices (slow cold start), well before the deterministic compute/retrieval layer (`compute.py`,
already tested against the full corpus per query, O(n) scan, sub-second at n=500 and still sub-second
at n=5,000 on any modern machine).

## 6 · What broke while building

The contact-field bug (`principal_email` populated from a firm's generic inbox instead of a named
person) — found by audit, fixed in `4b372f6`. The NVIDIA free-tier LLM call latency (130-380s per call)
was discovered empirically during this build and directly shaped the agent design: two LLM calls per
goal, not per candidate, and both grounded/rejectable rather than trusted blindly.

## 7 · Buyer challenge and demonstrated commercial value

[Filled in after Goal 3 is chosen and run — see submission email.]
