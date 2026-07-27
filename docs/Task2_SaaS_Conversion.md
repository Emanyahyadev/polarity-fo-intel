# Task 2 — SaaS Conversion Analysis

> **Candidate note:** this is my reasoning to own and defend at the Ownership Check, not consulting advice for adoption. The question is deliberately underspecified; the point is how I reason under that uncertainty, not a prescription. *(Draft for the candidate to revise into their own voice.)*

**The question:** a SaaS providing Family Office Intelligence converts 3% of free accounts to paid; the founders want to increase MRR. How would I improve the free-to-paid conversion rate?

## First: I would not accept the question as framed

The instinct is to reach for the standard PLG conversion playbook — onboarding emails, social proof, urgency, shorten time-to-value, add paywall triggers. That answer is identical for any SaaS, and for *this* business it is probably wrong. Three reasons:

1. **3% of what, and is 3% even the problem?** 3% of 300 signups and 3% of 300,000 are different companies with different problems. And 3% is only "bad" against a benchmark that assumes self-serve PLG. This product sells **family-office intelligence to institutional allocators** — a high-ACV, low-volume, trust-based, high-consideration purchase. That buyer does not swipe a card after a free trial; they buy on data accuracy, coverage, and trust, often through a relationship. Importing a $30/month PLG benchmark onto an enterprise-sold product is the first mistake.
2. **The goal is MRR, not conversion rate.** MRR = f(traffic quality, ICP fit, activation, price, expansion, retention). Conversion % is one term, and optimising it can *lower* MRR (e.g. converting more low-fit users who churn). Some of the highest-MRR moves here would *reduce* free signups.
3. **Is conversion even the binding constraint?** It might be traffic quality, pricing, data trust, or retention. I would not spend a dollar improving 3% until I know which.

## What I would need to know (what's missing)

Before prescribing anything, I'd get: the **definition** of "free account" and "paying user" (freemium vs trial; self-serve vs sales-assisted); the **ACV and current price**; **volume** (is the numerator or denominator the issue?); the **acquisition channel and ICP fit** (are free users actually allocators/family offices, or students, competitors, and tyre-kickers?); **where in the funnel** users drop (signup → activation → willingness-to-pay → procurement/close); **who buys** (in a fund or family office the analyst trials it but the CIO/partner pays — a champion-vs-economic-buyer split); and **cohort retention + expansion**. Without these, any tactic is a guess.

## Segment before prescribing

A 3% conversion has at least three distinct root causes, each with a different fix:
- **Can't get value (activation).** The free experience doesn't reach a "decision-grade insight" moment — thin coverage, stale data, no time-to-first-insight. *For this product specifically, data quality is the product* — if the free tier surfaces unverified or shallow records, no serious allocator will trust it enough to pay. Fix: coverage + a visible trust layer (confidence, provenance, "verified via" — exactly what this assessment's dataset makes possible).
- **Got value but won't pay (pricing/packaging).** WTP mismatch, wrong package boundaries, or — common with high-ACV data products — *under-pricing that destroys credibility*. Fix: repackage around the job (targeting a raise, sourcing co-investors), price to the buyer's budget, add a sales-assist for qualified accounts.
- **Wrong buyer in the funnel (targeting).** The free tier attracts non-buyers. Fix: qualify signups and route high-fit accounts to a human. This *lowers* the conversion-rate denominator but *raises* MRR.

## The likely-highest-leverage move

For a trust-based, high-ACV intelligence product, the binding constraint is usually **data trust × buyer qualification**, not funnel micro-copy. I'd bet the biggest MRR unlock is a **qualified, sales-assisted motion for high-fit accounts** (a $20–60k/yr allocator will not self-serve) combined with a **visible verification layer** that earns trust in the free experience — with expansion/retention (net revenue retention) mattering more than new conversion at this ACV.

## How I would test it (test reality → extract signal → classify → act)

Not a plan to build; a plan to *learn*, cheapest signal first:
1. **Instrument + segment the funnel** by ICP fit → is 3% a targeting, activation, or pricing problem? (1–2 days, no build.)
2. **Talk to 20 who converted and 20 who didn't** → why-buy / why-not. Highest signal-per-hour input there is.
3. **Test a sales-assist motion** on high-fit accounts vs. a self-serve control → does human touch move MRR at this ACV?
4. **Test packaging + price** (van Westendorp / a live price test) and a **"verified data" trust signal** in the free tier → does trust or price move WTP?
5. For each test, **state up front what signal confirms or refutes it**, and run them in order — build only when a signal justifies it.

## Honest uncertainty

I don't have the internal data, so this is a **diagnostic framework and experiment sequence**, not an answer. My core claim — the one I'd defend — is that treating this as a PLG-conversion-optimisation problem is the trap; the leverage is in **buyer qualification, data trust, pricing, and retention**, measured against MRR rather than a conversion percentage.
