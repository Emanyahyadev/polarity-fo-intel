# Validation Chains — 3 Records

Full provenance for three delivered records, one per discovery lens. Each shows: discovery source → extraction → enrichment → validation logic → confidence → exact sources, plus the **deep intelligence** now carried (principal, AUM, recent activity) and the **honest `could_not_verify`** blanks. Each is reproducible by an independent reviewer in a few minutes.

---

## 1 · Callan Family Office, LLC  (`fo_beb7590905`) — SEC lens, Medium confidence, full depth

| Step | Detail |
|---|---|
| **Discovery source** | SEC EDGAR full-text search for "family office" over 13F filings (`efts.sec.gov`) surfaced the filer + CIK. |
| **Enrichment 1 (authoritative)** | `data.sec.gov/submissions/CIK{cik}.json` → legal name, business address **Radnor, PA**, firm phone **+1 (267) 250-2036**, EIN. Snapshotted (sha256). |
| **Enrichment 2 (independent)** | SEC IAPD / Form ADV (`api.adviserinfo.sec.gov`) → registered investment adviser whose name states "family office". A *different filing system* from EDGAR 13F → independent authoritative source. |
| **Enrichment 3 (independent)** | Official website `https://callanfamilyoffice.com/` fetched and confirmed family-office self-description. |
| **Enrichment 4 (deep, SEC Form 13F filing)** | The firm's own 13F yields, from the filing itself: **principal — John Ginter, CEO and CCO**, direct line **+1 (267) 250-2036**; **AUM — $4.41B in 13(f) securities as of 03-31-2026** (1,131 positions); **recent investments — new Q1-2026 positions** (Abbott Laboratories, Affiliated Managers Group, Agree Realty, Air Products …). Dated, content-hashed. |
| **Validation logic** | Rule 2 satisfied by **four independent authoritative signals** (13F existence, ADV registration, firm website, 13F filing) → qualifies. Passes all 9 release gates. |
| **Confidence** | **Record: High.** **Type: Undetermined** — *candour:* no explicit single-/multi-family language in the evidence, so not asserted. |
| **Honesty (candour built into the record)** | `reviewer_notes`: the principal is the firm's **13F signatory** (a named officer, title exactly as filed — commonly CCO/GC, *not necessarily the lead investor*); `estimated_aum` is the **aggregate 13(f) securities value, not total AUM**. `could_not_verify`: corporate LinkedIn, principal LinkedIn, principal work email — not exposed by free authoritative sources, recorded rather than guessed. |
| **Reproduce** | Search "Callan Family Office" on `https://adviserinfo.sec.gov` (ADV) and `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&type=13F` (13F filing → cover page + information table); open `https://callanfamilyoffice.com/`. |

---

## 2 · Matter Family Office  (`fo_a4cb68cd35`) — IAPD-registry lens, type resolved

| Step | Detail |
|---|---|
| **Discovery source** | SEC IAPD / Form ADV registry search for "family office" (`api.adviserinfo.sec.gov`) — surfaces registered family offices that do **not** file 13F (invisible to the EDGAR lens). |
| **Enrichment 1 (authoritative)** | The ADV registration confirms the registered family-office entity + St Louis, MO address. |
| **Enrichment 2 (independent)** | Official website `https://www.matterfamilyoffice.com/` fetched → describes a **multi-family office**, and yields the firm's stated **investment thesis: *"We believe wealth should enhance your life and support your purpose."*** (an attributable quote from its own site). |
| **Validation logic** | Two independent authoritative sources (ADV + website) → qualifies; website language resolves **type = Multi-Family Office**. |
| **Confidence** | **Record: Medium · Type: High (MFO).** |
| **Honesty** | Does **not** file 13F, so principal / direct phone / AUM are honest `could_not_verify` (no fabricated contact, no scraped AUM). |
| **Reproduce** | `https://adviserinfo.sec.gov` (search "Matter Family Office"); `https://www.matterfamilyoffice.com/`. |

---

## 3 · Revisio Family Office  (`fo_33a7413d76`) — directory lens, discovery ≠ verification

| Step | Detail |
|---|---|
| **Discovery source** | Curated directory — Wikidata "family office" (`Q751314`) / Wikipedia. **Discovery-only**: per the inclusion standard + release gate, community-edited references may **never** verify a firm. |
| **Enrichment (authoritative, independent of discovery)** | Fetched the firm's official website `https://revisio-family.de/` and confirmed **family-office self-description** (German). This is the verification (FIRM_SITE ≠ the DIRECTORY discovery source → passes the independence gate). |
| **Validation logic** | Rule 2 satisfied by the firm's own website (authoritative, non-discovery-only). Type single-vs-multi not stated → honest **Undetermined**. |
| **Confidence** | **Record: Medium · Type: Undetermined.** *Honest limitation:* a non-US office (the product targets the US) — included as validated but flagged. |
| **Honesty** | `could_not_verify`: principal (name/title/phone), AUM, corporate/principal LinkedIn, work email — none available from an authoritative public source for this firm; all recorded, none guessed. |
| **Reproduce** | `https://www.wikidata.org/wiki/Q751314` (discovery); `https://revisio-family.de/` (verification). |

---

**Cross-cutting guarantees** (checkable in the repo): every populated high-value cell carries provenance (Rule 1); discovery is kept separate from verification (a firm's *own* filing/site verifies it, never the directory it was found in); anything that could not be verified from an authoritative source is a recorded `could_not_verify` blank, never a guess (findings govern releases); each fetch is content-hash snapshotted for reproducibility.
