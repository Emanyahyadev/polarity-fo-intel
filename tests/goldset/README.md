# Rediscovery gold set — internal evaluation fixture

**These records are used only to evaluate autonomous rediscovery and are excluded from
production acquisition.**

## What this is

`raw_source.jsonl` is a disclosed, documented list of organization names (with the
country/city/website/email/phone an external lookup found for them) used as an
evaluation oracle: can the autonomous discovery pipeline — starting from the
organization's **name only** — independently find the same entity through the real,
production discovery path (Tavily / Exa / Serper, domain resolution, evidence
extraction, classification, the real release gate) and arrive at comparable evidence?

## Provenance of the raw list

The names, websites, phone numbers, and emails in `raw_source.jsonl` were gathered by
an external browser-automation lookup the user ran independently (not this repository's
pipeline, not built or executed by this session against LinkedIn or any access-controlled
source — see the session record for the explicit refusal of the LinkedIn/pattern-email
variant of this request). This is a documented **subset** (86 of a larger externally
generated list) chosen for a tractable first baseline run within this session's time
budget. It is stored here, disclosed, precisely so its existence and origin are part of
the record — not hidden from documentation, commit history, or the AI working-session
record, per explicit instruction.

## Rules enforced by `scripts/goldset_rediscovery.py`

- The rediscovery run receives **only `candidate_name`** from each fixture row — never
  the website, email, phone, or address. Those fields exist in the fixture solely as the
  post-hoc comparison target, read only AFTER the autonomous run completes.
- Gold-set records are **never** written to `data/final`, never counted toward the
  500-record target or the 200-named-person-email target, never enter the production RAG
  index, and never appear in customer-facing search results or stats.
- A gold-set record is only ever reported as "autonomously discovered" if the production
  discovery/enrichment/classification path actually produced that result at runtime — the
  fixture's own `website`/`verified_email` fields are never substituted for a real result.
- Contact-quality scoring applies the exact Differentiator standard: `info@` / `contact@`
  / `office@` / `hello@` / `enquiries@` / `welcome@` and similar generic mailboxes are
  **never** counted as a named-person professional email, including when the fixture's own
  external source labeled them `verified_email` — that label describes the external tool's
  standard, not this project's.
- Family-office classification uses the real `firm_type`/gate logic. A fixture entry
  self-describing as a family office in marketing copy is not accepted as evidence; the
  gold set evaluates the system, it does not override policy. Fixture rows with
  `possible_type: "UNKNOWN"` are included and are expected to often fail qualification —
  that is a correct outcome, not a bug.

## How to run

```
python scripts/goldset_rediscovery.py [N]      # N = sample size, default: full fixture
```

Output is written to `docs/evidence/goldset-rediscovery-BASELINE.json` (first run) and
`docs/evidence/goldset-rediscovery-AFTER.json` (post-fix reruns), never to `data/final`.
