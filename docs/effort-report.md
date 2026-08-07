# Effort Report — Methodology & Template

## Purpose

The build-session summary states how the work was done and why, but it deliberately
does **not** state a total person-hour figure, because no trustworthy basis for one
exists in the repository. This document is the methodology the candidate uses to
produce that figure herself, plus a blank template for her to fill and commit.

## Why no machine-derived estimate

An earlier draft derived "18–20 hours" from git commit timestamps. That number is
**not** a measurement of effort:

- A commit timestamp captures when a change was *pushed/saved*, not how long the work
  took. Analysis, reading, designing, debugging, and verifying happen between commits
  and are invisible to git.
- Long idle gaps inside commit windows, machine-aided drafting, and parallel work all
  distort a timestamp span. **Timestamps measure a span of wall-clock time, not
  effort.**
- Treating timestamps as effort would present a number the repository cannot actually
  support. No such figure is shipped.

Only a person who performed the work (and recorded it at the time) can report effort.
The repository's job is to be accurate; the candidate's job is to report effort they
can stand behind.

## How to fill it (for the candidate)

1. Read the numbered work phases in `docs/BuildSessionSummary.md`.
2. For each phase, enter only hours you can attribute to that phase, using your own
   records (scheduler logs, session notes, timestamps of real working sessions).
3. Do **not** convert wall-clock spans to hours; report active work only.
4. Where the work was assisted by AI tooling, report the total honestly; you are not
   required to split machine vs human time unless that helps you be accurate.
5. Add a short note on how each figure was recorded (the "source of truth" per line),
   so the report is auditable, not asserted.

## Template

```markdown
# Effort Report — <candidate name>, <submission>

Filled in by the candidate. Figures are the candidate's own, recorded per the
methodology in this file. They are NOT derived from commit timestamps.

## Per-phase effort (active work)

| Phase (see BuildSessionSummary) | Hours | Source of truth (how recorded / verified) |
|---|---|---|
| 1. Analysis + architecture |  |  |
| 2. Discovery |  |  |
| 3. Architecture Gate Review + remediation |  |  |
| 4. Enrichment + validation + dataset |  |  |
| 5. Micro-RAG + deploy |  |  |
| 6. Deep commercial intelligence |  |  |
| 7. Adversarial hardening + live deploy |  |  |

## Total

| Metric | Value |
|---|---|
| Total active build hours |  |
| Calendar window spanned (dates) |  |
| Notes on recording method |  |

## Verification statement (candidate)

I certify that the figures above record active work I performed, recorded as noted,
and that no number here is derived from commit timestamps as a proxy for effort.

Signed: ____________   Date: ____________
```

## Acceptance

The figure is the candidate's. This repository's build documents link to this
methodology and do not assert a number themselves.