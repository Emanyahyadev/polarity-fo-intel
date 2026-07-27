# Tradeoffs

Cross-cutting tensions we are navigating deliberately. (Component-level tradeoffs live in `DecisionLog.md`.)

## T1 — Sellable vs. honest (the central dataset tension)
The assessment demands a file that is **not mostly blanks** (must be sellable) *and* contains **no guessed values dressed as verified** (a failed-verification cell costs more than a blank). These pull against each other, hardest for the very SFOs that score highest — they hide, so their decision-maker contact data is the least verifiable.

**How we resolve it.** Verify what is genuinely verifiable on free tiers (domain/MX/SMTP for role/pattern emails with a status label; firm phone from authoritative filings; LinkedIn URL resolution; ≥2-source firm-fact corroboration). Where a *personal* cell can't be verified, ship an honest blank + `could_not_verify`, and compensate for actionability with **entity-level** intelligence (thesis, mandate, AUM, recent dated signals) that still tells a fund manager *why them, why now*. The **distribution** of verified-vs-blank, shown honestly, is itself the signal. We would rather ship a Medium-confidence record with two strong signals and a role email than a High-confidence claim we can't defend under sampling.

## T2 — Depth vs. breadth (where the hours go)
Priority order is fixed by the assessment: **dataset first, working functionality second, presentation third.** So depth concentrates on (a) discovery diversity + firm-type proof and (b) the grounding control — the two things most likely to be adversarially tested. We explicitly decline breadth (extra agents, extra sources, extra UI surface) that does not move those.

## T3 — Velocity vs. validation (the 45-hour clock)
How We Work: "velocity without validation is recklessness," but the window is real. We buy speed by **scoping small** (50 records, 3 sources, one focused UI) and spend the saved time on validation evidence (gold set, audit trail, live-query logs), not on more features. Slower-but-right beats fast-but-unverifiable here by design.

## T4 — Coverage vs. verification cost per record
Deep verification (SMTP probes, multi-source corroboration, signal dating) is slow per record. Rather than thinly enrich a large pool, we discover a pool of ~4× and spend verification budget only on records that clear the firm-type gate — so effort lands on records that can actually ship.

## T5 — Automation vs. judgment
The 50 must be pipeline-produced, not hand-assembled — but human judgment sets the inclusion standard, labels the gold set, and makes the SFO/MFO/Undetermined calls the classifier is unsure about. AI builds the pipeline; the human owns the standard. Those judgment points are logged in `BuildLog.md` so the reasoning is visible.
