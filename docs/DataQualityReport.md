# Data Quality, Coverage & Source-Diversity Report

*Family Office Intelligence — Task 1 dataset. Every figure below is recomputed by
`scripts/quality_report.py` from the delivered `data/final/family_offices.csv`; none
is hand-entered. Regenerate after any dataset change.*

**Headline:** 50 validated family-office records. All 50 pass the Rule-2 evidence
gate (`fo_type_evidence` present). Provenance completeness: **0
violations** across all populated high-value fields (Rule 1). No fabricated contact
data — unverifiable fields are blanked and named in `could_not_verify`.

## 1. Coverage

**Classification (honest, per the assessment's "say so if undetermined"):**
**27** Undetermined, **7** Single-Family Office, **16** Multi-Family Office

**Record confidence (weakest-link aggregate):** **28** High, **21** Medium, **1** Low

**Geography:** **46** United States, **1** Germany, **1** Monaco, **1** Brazil, **1** Switzerland
Top US states: **7** FL, **5** TX, **5** NY, **4** NC, **4** CA, **3** CO, **2** PA, **2** AL, **2** CT, **1** MO, **1** KS, **1** MA

**Field completeness**

| Field | Populated | % |
|-------|-----------|---|
| Website | 28/50 | 56% |
| Estimated AUM | 32/50 | 64% |
| Principal (name) | 35/50 | 70% |
| HQ phone (authoritative) | 28/50 | 56% |
| Investment thesis | 17/50 | 34% |
| ≥1 recent signal | 25/50 | 50% |
| Investing sectors | 1/50 | 2% |
| Corporate LinkedIn | 0/50 | 0% |

## 2. Source diversity & independence

**Discovery source (how the firm was FOUND):** **28** SEC EDGAR (13F / SC / Form D filings), **20** SEC IAPD / Form ADV (investment-adviser registration), **2** Curated directory / reference (Wikipedia, associations)

**Verification source (how facts were PROVEN; a record may carry several):**
**28** SEC EDGAR (13F / SC / Form D filings), **48** SEC IAPD / Form ADV (investment-adviser registration), **27** Firm Website

**Discovery ≠ verification:** 48/50 records are verified by at least one
authoritative source *of a different class* than the one that discovered them (e.g. a
13F-discovered firm confirmed against its independent SEC IAPD / Form ADV registration).

**AUM provenance:** 32/50 carry an AUM figure —
24 from Form 13F (13(f) securities), 8
from Form ADV Item 5.F (total regulatory AUM). Website-scraped AUM is deliberately
excluded as unreliable.

## 3. Verification depth & honesty

`could_not_verify` is used as an honesty ledger, not a dumping ground — a field is
listed **only** when we tried an authoritative source and it was not establishable
(the schema forbids a field being both populated and listed):

**50** corporate_linkedin, **50** principal_linkedin, **50** principal_email, **26** principal_phone, **15** principal_name, **15** principal_title, **18** estimated_aum, **1** website, **1** investment_thesis

Corporate LinkedIn, principal LinkedIn and principal email are blank for all 50
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

- **Discovery concentration:** 48/50
  records were discovered via SEC systems (EDGAR 13F + IAPD/ADV). SEC is the highest-signal
  free authoritative source for US advisers, but this skews the set US-heavy and toward
  registered/reporting firms. Non-SEC discovery (associations, curated references) is thin.
- **International coverage:** 4/50 records are outside the US — a known gap;
  free authoritative registries abroad are fragmented.
- **Contact enrichment:** corporate/principal LinkedIn and principal email are unverified
  across the set. These are verifiable through a licensed contact-data source (e.g. Apollo),
  which would be labelled honestly as a vendor source rather than a primary filing.
- **Type resolution:** 27/50 remain Undetermined —
  proven family offices whose single/multi sub-type is not stated on an authoritative
  source. These are labelled honestly rather than guessed.
