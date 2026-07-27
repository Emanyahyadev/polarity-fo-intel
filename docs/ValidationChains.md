# Validation Chains — 3 Records

Full provenance for three delivered records, one per discovery lens. Each shows: discovery source → extraction method → enrichment → validation logic → confidence → exact sources. These are verifiable in ~5 minutes by an independent reviewer.

---

## 1 · Pathstone Family Office, LLC  (`fo_38a12a7ca6`) — SEC lens, High confidence

| Step | Detail |
|---|---|
| **Discovery source** | SEC EDGAR full-text search for "family office" over 13F/SC filings (`efts.sec.gov`) surfaced the filer + CIK. |
| **Extraction** | Filer name + CIK parsed from the EDGAR search hit; CIK de-padded. |
| **Enrichment 1 (authoritative)** | `data.sec.gov/submissions/CIK{cik}.json` → legal name "PATHSTONE FAMILY OFFICE, LLC", business address **10 Sterling Blvd, Englewood, NJ 07631**, phone **+1 (201) 731-7112**, EIN. Snapshotted (sha256) for reproducibility. |
| **Enrichment 2 (independent)** | SEC IAPD / Form ADV (`api.adviserinfo.sec.gov`, CRD 151736) → registered aliases include **"PATHSTONE FAMILY OFFICE, LLC"** and **"STONE TOWER FAMILY OFFICE, LLC"**; office address matches. IAPD (IARD) is a *different filing system* from EDGAR 13F → an independent authoritative source. |
| **Validation logic** | Rule 2 satisfied by two independent authoritative sources naming it a family office → **qualifies**, `fo_type_confidence = High`. Firm phone + address are authoritative. Passes all 9 release gates. |
| **Confidence** | **Record: High** (two independent authoritative verifications). **Type: Undetermined** — *candour:* Pathstone is publicly a large multi-family office (162 branches), but the automated evidence chain did not contain explicit "multi-family" language, so we label Undetermined rather than assert MFO. |
| **Exact sources** | `https://www.sec.gov/cgi-bin/browse-edgar?...CIK=1511137`; `https://data.sec.gov/submissions/CIK0001511137.json`; `https://adviserinfo.sec.gov/firm/summary/151736` |

---

## 2 · Matter Family Office  (`fo_a4cb68cd35`) — IAPD-registry lens, type resolved

| Step | Detail |
|---|---|
| **Discovery source** | SEC IAPD / Form ADV registry search for "family office" (`api.adviserinfo.sec.gov`) — surfaces registered family offices that do **not** file 13F (invisible to the EDGAR lens). |
| **Extraction** | Firm name, CRD, and office address (St Louis, MO) parsed from the registry record; only firms whose registered name/aliases contain "family office" are kept. |
| **Enrichment 1 (authoritative)** | The ADV registration itself confirms the registered family-office entity + address. |
| **Enrichment 2 (independent)** | Official website resolved by constructed domain and **verified by fetching** `https://www.matterfamilyoffice.com/` — the site describes a **multi-family office** ("family office services … investing, wealth planning, family learning …"). Independent of the registry. |
| **Validation logic** | Two independent authoritative sources (ADV registration + firm website) → **qualifies**; website language resolves **type = Multi-Family Office** (`fo_type_confidence = High`). Actionability satisfied by the website. |
| **Confidence** | **Record: Medium** · **Type: High (MFO)**. |
| **Exact sources** | `https://adviserinfo.sec.gov/firm/summary/{crd}`; `https://www.matterfamilyoffice.com/` |

---

## 3 · Revisio Family Office  (`fo_33a7413d76`) — directory lens, discovery ≠ verification

| Step | Detail |
|---|---|
| **Discovery source** | Curated directory — Wikidata instance of "family office" (`Q751314`) / Wikipedia. **Discovery-only**: Wikipedia/Wikidata are community-edited and, by our inclusion standard + release gate G5, may **never** verify a firm. |
| **Extraction** | Firm name + Wikidata official-website property (P856). |
| **Enrichment (authoritative, independent of discovery)** | Fetched the firm's official website `https://revisio-family.de/` and confirmed **family-office self-description** (German: "Ganzheitliche Betreuung von Familieninteressen …"). This is the authoritative verification (FIRM_SITE ≠ the DIRECTORY discovery source → passes independence gate G6). |
| **Validation logic** | Rule 2 satisfied by the firm's own website (authoritative, non-discovery-only). Type single-vs-multi not stated → honest **Undetermined**. Location: Germany. |
| **Confidence** | **Record: Medium** · **Type: Undetermined**. *Honest limitation:* a non-US office (the product targets the US market) — included as a validated record but flagged. |
| **Exact sources** | `https://www.wikidata.org/wiki/` (discovery); `https://revisio-family.de/` (verification) |

---

**Cross-cutting guarantees** (verifiable in the repo): every populated high-value cell carries provenance (Rule 1); discovery is kept separate from verification; nothing that failed validation appears in a delivered field (release gate G9); each fetch is content-hash snapshotted for reproducibility.
