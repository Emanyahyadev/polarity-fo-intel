# Data Quality, Coverage & Source-Diversity Report

*Family Office Intelligence — Task 1 dataset. Every figure below is recomputed by
`scripts/quality_report.py` from the delivered `data/final/family_offices.csv`; none
is hand-entered. Regenerate after any dataset change.*

**Headline:** 215 validated family-office records. All 215 pass the Rule-2 evidence
gate (`fo_type_evidence` present). Provenance completeness: **514
violations** across all populated high-value fields (Rule 1). No fabricated contact
data — unverifiable fields are blanked and named in `could_not_verify`.

## 1. Coverage

**Classification (honest, per the assessment's "say so if undetermined"):**
**48** Multi-Family Office, **139** Undetermined, **28** Single-Family Office

**Record confidence (weakest-link aggregate):** **162** Medium, **53** Low

**Geography:** **115** United States, **4** Germany, **6** Switzerland, **1** Monaco, **3** Brazil, **3** France, **2** Denmark, **1** Belgium, **3** unknown, **4** United Kingdom, **2** United Arab Emirates, **4** Singapore, **2** Hong Kong, **7** Canada, **5** Australia, **2** Spain, **1** Italy, **5** Netherlands, **3** Sweden, **3** Norway, **4** Austria, **4** India, **2** Luxembourg, **1** Qatar, **1** Kuwait, **2** Israel, **1** Turkey, **1** Hungary, **1** Kenya, **2** Malaysia, **3** Thailand, **2** Chile, **1** Argentina, **1** Colombia, **4** South Africa, **1** Sri Lanka, **7** Saudi Arabia, **1** Oman
Top US states: **22** FL, **16** NY, **15** ?, **10** CA, **8** TX, **6** CO, **5** NC, **4** PA, **4** AZ, **4** AL, **3** WA, **3** IA

**Field completeness**

| Field | Populated | % |
|-------|-----------|---|
| Website | 194/215 | 90% |
| Estimated AUM | 9/215 | 4% |
| Principal (name) | 17/215 | 8% |
| HQ phone (authoritative) | 29/215 | 13% |
| Investment thesis | 138/215 | 64% |
| ≥1 recent signal | 0/215 | 0% |
| Investing sectors | 0/215 | 0% |
| Corporate LinkedIn | 0/215 | 0% |

## 2. Source diversity & independence

**Discovery source (how the firm was FOUND):** **29** SEC EDGAR (13F / SC / Form D filings), **54** SEC IAPD / Form ADV (investment-adviser registration), **13** Curated directory / reference (Wikipedia, associations), **116** Other, **1** IRS 990-PF (ProPublica Nonprofit Explorer), **1** Web search (EXA), **1** Web search (Tavily)

**Verification source (how facts were PROVEN; a record may carry several):**
**100** SEC IAPD / Form ADV (investment-adviser registration), **29** SEC EDGAR (13F / SC / Form D filings), **192** Firm Website

**Discovery ≠ verification:** 204/215 records are verified by at least one
authoritative source *of a different class* than the one that discovered them (e.g. a
13F-discovered firm confirmed against its independent SEC IAPD / Form ADV registration).

**AUM provenance:** 9/215 carry an AUM figure —
0 from Form 13F (13(f) securities), 9
from Form ADV Item 5.F (total regulatory AUM). Website-scraped AUM is deliberately
excluded as unreliable.

## 3. Verification depth & honesty

`could_not_verify` is used as an honesty ledger, not a dumping ground — a field is
listed **only** when we tried an authoritative source and it was not establishable
(the schema forbids a field being both populated and listed):

**215** corporate_linkedin, **211** principal_linkedin, **213** principal_email, **198** principal_name, **198** principal_title, **215** principal_phone, **206** estimated_aum, **11** hq_phone, **40** firm_contact_email

Corporate LinkedIn, principal LinkedIn and principal email are blank for all 215
records: none could be authoritatively verified from free public sources, so none were
guessed. This is the single biggest enrichment opportunity (see §6).

## 4. SEC registration-status audit

Every IAPD-mapped firm's live registration status was re-checked against the SEC IAPD
firm API. **5 firms are inactive/withdrawn.** A withdrawn registration is
common and often *expected* for a genuine family office — single-family offices are
excluded from the definition of investment adviser under the SEC Family Office Rule and
routinely deregister. Each inactive firm is kept only where independent operating
evidence exists, and every one carries an explicit status note:

| Firm | CRD | Independent operating evidence | Disposition |
|------|-----|-------------------------------|-------------|
| Carpa Family Office | 329017 | verified firm website | kept + noted |
| Holdun Family Office | 158123 | verified firm website | kept + noted |
| Wealthgate Family Office | 307858 | recent Form 13F (2024-09-30) | kept + noted |
| Geller Advisors | 134062 | Form ADV AUM ($5.01B) + 13F | kept + noted |
| The Family Office, LLC | 288530 | none (see §5) | reset to IAPD facts only |

## 5. Contamination correction (self-caught)

`THE FAMILY OFFICE, LLC` (CRD 288530, Redmond WA) has a fully generic name with no
distinctive token, which had caused an **unrelated** company's website —
`thefamilyoffice.com`, a residential real-estate advisory — to be attached during
enrichment, contaminating its website, description, thesis, principal and type. On
re-verification this was caught, all website-derived fields were removed, and the record
was reset to only what SEC IAPD authoritatively supports (name, Redmond WA location,
family-office registration; registration now inactive). Everything else is flagged
`could_not_verify`. A generic-name guard now prevents this class of mismatch at the
source. Fully reproducible: `scripts/correct_contamination.py`.

## 6. Gaps & known limitations (honest)

- **Discovery concentration:** 83/215
  records were discovered via SEC systems (EDGAR 13F + IAPD/ADV). SEC is the highest-signal
  free authoritative source for US advisers, but this skews the set US-heavy and toward
  registered/reporting firms. Non-SEC discovery (associations, curated references) is thin.
- **International coverage:** 94/215 records are outside the US — a known gap;
  free authoritative registries abroad are fragmented.
- **Contact enrichment:** corporate/principal LinkedIn and principal email are unverified
  across the set. These are verifiable through a licensed contact-data source (e.g. Apollo),
  which would be labelled honestly as a vendor source rather than a primary filing.
- **Type resolution:** 139/215 remain Undetermined —
  proven family offices whose single/multi sub-type is not stated on an authoritative
  source. These are labelled honestly rather than guessed.
