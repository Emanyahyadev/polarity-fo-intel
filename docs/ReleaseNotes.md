# Final Release Candidate — Repair & Sign-off Notes

*Principal-engineer repair pass on the family-office intelligence deliverable
(dataset + Micro-RAG). Every number here is reproduced by a committed script; the
canonical source of truth is `data/final/records.json` (the CSV/XLSX are exported from
it). Date: 2026-07-28.*

## 1. Why this pass happened

An independent 4-lens adversarial review (senior-FDE reviewers, read-only, told to break
the work) scored the submission and found the **dataset axis — the pass/fail product — at
6/10** with two `[High]` findings that a 5-minute check surfaces:

1. **Rule 1 provenance was reconstructed, not delivered** — the shipped Provenance sheet
   had a resolvable `source_url` on only 28/345 cells; the "0 violations" headline held
   only because a report-time `reconstruct()` backfilled generic entries.
2. **The SFO tier was mislabeled** — e.g. `WE FAMILY OFFICES` (a $10.2B **regulatory**-AUM
   registered adviser that "partners with families") was typed Single-Family Office, the
   exact error the brief forbids.

Plus: an empty Audit sheet, wiped `reviewer_notes`, homogeneous 13F-only signals, and
stale doc counts. Several were regressions introduced by a lossy CSV round-trip in the
enrichment scripts. This pass repairs all of them at the source.

## 2. Changelog (what was repaired)

| # | Defect | Repair | Evidence |
|---|--------|--------|----------|
| 1 | **Rule 2** — 8 mislabeled SFOs | Re-verified single-vs-multi against each firm's own website; reclassified on an explicit quote or regulatory-AUM fact. SFO **12→4**, MFO **16→21**, Undetermined **27→30**. | `scripts/reverify_types.py`, `data/adv/type_reverify.json`, Audit sheet |
| 2 | **Rule 1** — provenance reconstructed | Rebuilt as a **lossless canonical store** (`records.json`); attached a real, resolvable `source_url` to **all 386** provenance cells (IAPD firm-summary from CRD, EDGAR 13F filing list from CIK + retained snapshot hash, firm website). **0 native provenance violations** (no `reconstruct()`). | `scripts/finalize_release.py`, `tests/test_release_integrity.py` |
| 3 | Wiped `reviewer_notes` | Restored contamination-correction note, inactive-registration status notes, and a classification-change note per reclassified firm. **16/55** populated. | store, CSV |
| 4 | Empty Audit sheet | Emitted a **23-row** Audit trail (reclassifications, contamination strip, principal_phone withholdings). Gate G9 no longer vacuous. | xlsx `Audit` sheet |
| 5 | Misleading `principal_phone` | Blanked where it merely repeated the SEC firm main line (not a verified direct line) → `could_not_verify`, with an Audit entry each. | Audit sheet |
| 6 | Signals mislabeled `NEWS` | 13F-derived signals now carry `source_class = SEC_EDGAR` with the EDGAR filing URL; described honestly as recent 13F portfolio activity. | store |
| 7 | Stale doc counts | Reconciled every doc to **55 records / 18-18 RAG eval / recall 0.50 / 8 FNs**. | docs sweep |
| 8 | Reproducibility gap | Pinned the RAG/serve stack (`requirements-serve.txt`); added **6 release-integrity tests** that bind docs↔data so counts can't drift again. | `requirements-serve.txt`, `tests/test_release_integrity.py` |

## 3. Provenance model (Rule 1, honest scope)

True per-filing-accession lineage was not recoverable for every historical cell without
re-fetching, so — per the "strongest consistent model, never fake it" standard — every
populated high-value cell now carries a **real, resolvable authoritative URL**:

- **Registration / identity / ADV AUM** → `https://adviserinfo.sec.gov/firm/summary/{CRD}` (40 firms have a CRD).
- **13F AUM / signatory / holdings signals** → the firm's SEC EDGAR 13F filing list (`…&CIK={CIK}&type=13F`), plus a **content hash** from the retained EDGAR submissions snapshot where available (27 firms have a CIK).
- **Website-derived fields** (type, description, thesis, directory principals) → the firm website URL.

Distribution: **IAPD 144, EDGAR 114, Website 128** provenance cells; **386/386 carry a `source_url`**. `content_hash`/`snapshot_path` are populated for EDGAR-sourced cells and left empty (not faked) elsewhere.

## 4. Validation & regression (all green)

- **Unit/integration tests:** 96 passed, 1 skipped (`pytest -q`).
- **RAG grounding/abstention eval:** **18/18** — includes international queries and a new regression test that a reclassification left **no true SFO in Texas** (so `single-family offices in Texas` correctly abstains).
- **Firm-type gold set (n=25):** precision **1.0**, false-positive rate **0.0**, recall **0.50**, 8 named false negatives (4 of which — KIRKBI, Korys, Financière Agache, Builders Vision — are now recovered into the delivered set via website verification).
- **Integrity:** 0 duplicate ids/names/domains, 0 provenance violations, 0 populated-but-`could_not_verify` (native, from the store).

## 5. Release-gate checklist

- [x] No duplicate entities (id / name / domain)
- [x] Every populated high-value cell carries provenance **with a resolvable source_url**
- [x] Classification evidence exists for every record; **every SFO is a genuine single family** (no "not established" evidence, no regulatory client AUM)
- [x] Confidence honest (Undetermined not guessed; contact fields blank, not fabricated)
- [x] Dataset internally consistent (store = CSV = XLSX = stats report)
- [x] Documentation consistent (55 / 18-18 / recall 0.50 everywhere current)
- [x] Audit sheet non-empty (findings govern releases)
- [x] `reviewer_notes` restored; inactive registration surfaced in the record
- [x] Tests passing (96) + new anti-drift release-integrity tests
- [x] Reproducible: pipeline entrypoints documented; serve deps pinned

## 6. Reproducibility (honest)

- The **base dataset** rebuilds from public sources via `scripts/run_pipeline.py` (discovery) and `scripts/build_dataset.py` (enrich → gate → select → export), given network access + a descriptive User-Agent. Deterministic `fo_id`; `requirements.lock` pins the pipeline stack; `requirements-serve.txt` now pins the serving stack.
- The **enrichment + finalize passes** (`enrich_firecrawl.py`, `verify_directory.py`, `build_directory_records.py`, `reverify_types.py`, `correct_contamination.py`, `finalize_release.py`) are committed and re-runnable, but depend on external services (SEC IAPD/EDGAR, Firecrawl, Groq) and the candidate store `data/fointel.db`. A clean checkout reproduces the release with those keys + network; the run-manifests under `docs/evidence/` are **immutable historical logs** of past runs and are intentionally not rewritten.

## 7. Estimated score: before → after

- **Before this pass:** ~7/10 overall (dataset 6, RAG 9, validation 8, engineering 8).
- **After this pass:** *(appended below after the independent re-review of the repaired release)*
