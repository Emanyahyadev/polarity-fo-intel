# Data Quality, Coverage & Source-Diversity Report

*Family Office Intelligence — Task 1 dataset. Every figure below is recomputed by
`scripts/quality_report.py` from the delivered `data/final/family_offices.csv`; none
is hand-entered. Regenerate after any dataset change.*

**Headline:** 68 validated family-office records. All 68 pass the Rule-2 evidence
gate (`fo_type_evidence` present). Provenance completeness: **0
violations** across all populated high-value fields (Rule 1). No fabricated contact
data — unverifiable fields are blanked and named in `could_not_verify`.

## 1. Coverage

**Classification (honest, per the assessment's "say so if undetermined"):**
**14** Multi-Family Office, **54** Undetermined

**Record confidence (weakest-link aggregate):** **14** Medium, **54** Low

**Geography:** **64** United States, **1** Germany, **1** Switzerland, **1** Monaco, **1** Brazil
Top US states: **11** FL, **7** NY, **6** CA, **5** NC, **5** CO, **5** TX, **3** PA, **2** WA, **2** AZ, **2** CT, **2** AL, **2** OH

**Field completeness**

| Field | Populated | % |
|-------|-----------|---|
| Website | 47/68 | 69% |
| Estimated AUM | 8/68 | 12% |
| Principal (name) | 9/68 | 13% |
| HQ phone (authoritative) | 30/68 | 44% |
| Investment thesis | 33/68 | 49% |
| ≥1 recent signal | 0/68 | 0% |
| Investing sectors | 0/68 | 0% |
| Corporate LinkedIn | 0/68 | 0% |

## 2. Source diversity & independence

**Discovery source (how the firm was FOUND):** **30** SEC EDGAR (13F / SC / Form D filings), **36** SEC IAPD / Form ADV (investment-adviser registration), **2** Curated directory / reference (Wikipedia, associations)

**Verification source (how facts were PROVEN; a record may carry several):**
**30** SEC EDGAR (13F / SC / Form D filings), **47** Firm Website, **57** SEC IAPD / Form ADV (investment-adviser registration)

**Discovery ≠ verification:** 59/68 records are verified by at least one
authoritative source *of a different class* than the one that discovered them (e.g. a
13F-discovered firm confirmed against its independent SEC IAPD / Form ADV registration).

**AUM provenance:** 8/68 carry an AUM figure —
0 from Form 13F (13(f) securities), 8
from Form ADV Item 5.F (total regulatory AUM). Website-scraped AUM is deliberately
excluded as unreliable.

## 3. Verification depth & honesty

`could_not_verify` is used as an honesty ledger, not a dumping ground — a field is
listed **only** when we tried an authoritative source and it was not establishable
(the schema forbids a field being both populated and listed):

**68** corporate_linkedin, **68** principal_linkedin, **68** principal_email, **59** principal_name, **59** principal_title, **68** principal_phone, **60** estimated_aum

Corporate LinkedIn, principal LinkedIn and principal email are blank for all 68
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

- **Discovery concentration:** 66/68
  records were discovered via SEC systems (EDGAR 13F + IAPD/ADV). SEC is the highest-signal
  free authoritative source for US advisers, but this skews the set US-heavy and toward
  registered/reporting firms. Non-SEC discovery (associations, curated references) is thin.
- **International coverage:** 4/68 records are outside the US — a known gap;
  free authoritative registries abroad are fragmented.
- **Contact enrichment:** corporate/principal LinkedIn and principal email are unverified
  across the set. These are verifiable through a licensed contact-data source (e.g. Apollo),
  which would be labelled honestly as a vendor source rather than a primary filing.
- **Type resolution:** 54/68 remain Undetermined —
  proven family offices whose single/multi sub-type is not stated on an authoritative
  source. These are labelled honestly rather than guessed.
