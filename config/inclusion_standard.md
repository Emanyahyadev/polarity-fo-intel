# Inclusion Standard (Policy)

This is the human-authored policy that the validation layer enforces in code. It defines what may enter the dataset and what may not. It is deliberately strict: in this domain, **presenting an unconfirmed firm as a proven family office is the most serious error**, so the burden of proof sits on inclusion, not exclusion.

Two rules govern everything (they are separate):

- **Rule 1 — cells.** Every populated high-value cell carries its basis (source + method + confidence). A cell we could not verify is left blank and marked `could_not_verify`. Enforced by `provenance_violations()` + the release gate.
- **Rule 2 — the firm.** A record qualifies only with **affirmative evidence the firm is a family office**. A firm does **not** qualify because its name contains "family", because it serves wealthy clients, or because it appeared in a family-office-associated source. Enforced by `qualifies()` (requires `fo_type_evidence`) + the release gate.

A perfectly verified email on an unconfirmed firm is a verified cell on a **disqualified record**. Rule 2 is not satisfied by Rule 1.

---

## What counts as a family office (qualifying categories)

### 1. Single-Family Office (SFO) — the prize
The private entity managing **one** family's wealth/affairs. Often invisible (no website/marketing).

- **Required evidence (to include AND type as SFO):** affirmative evidence the entity manages the wealth of a *single* identified family and does **not** serve external clients. Examples: a SEC filing whose language describes a single-family investment office; a reputable reference (Wikidata/Wikipedia) classifying it as the family office/investment vehicle of a named family; credible press describing "the [Family] family office."
- **Acceptable evidence:** SEC 13F/SC filer described/known as a single-family office; Wikidata instance-of *family office* tied to one family; the firm's own site stating it serves one family.
- **Insufficient evidence:** the word "family" in the name; presence in a family-office list; being a private foundation (see §4); "we serve ultra-high-net-worth families" (that is marketing, and usually indicates an MFO/advisory).
- **Automatic rejection as SFO:** any evidence it serves **multiple** families or external clients → re-evaluate as MFO, do not label SFO.
- **Manual-review trigger:** single vs. multiple families unclear.

### 2. Multi-Family Office (MFO)
Provides family-office services to a **small number** of families; markets itself and publishes its team.

- **Required evidence:** the firm describes/positions itself as a family office serving multiple families (site, registration, reputable profile).
- **Acceptable evidence:** firm website "multi-family office"; ADV/registration describing multi-family services; reputable directory classification.
- **Insufficient evidence:** a generic RIA/wealth manager with no family-office service model; "wealth management for families."
- **Automatic rejection:** a broker-dealer/RIA serving the general public with no family-office positioning → §6 non-qualifying.
- **Manual-review trigger:** MFO vs. general wealth-management RIA.

### 3. Investment Office / Family Investment Vehicle
The investment arm of a family's wealth that may **not** use "family office" in its name (e.g., Bezos Expeditions, Walton Enterprises, Cascade-style vehicles).

- **Required evidence:** evidence it is the private investment vehicle of a specific family's/principal's wealth (not a fund raising outside capital).
- **Acceptable evidence:** reputable classification as a family office/family investment vehicle; credible press tying it to one family's capital.
- **Type:** treat as **SFO** if one family; **Undetermined** if the family structure is proven-FO but single/multi cannot be established.
- **Automatic rejection:** a fund that raises and manages **external** LP capital (that is a PE/VC/hedge fund, not a family office) → §6.

### 4. Private Foundation (IRS 990-PF) — a LEAD, not a family office
A family **foundation** is a philanthropic entity. It is **not** itself a family office.

- **Required evidence to qualify a record from this lead:** *separate* affirmative evidence that the family operates a family-office entity distinct from the foundation.
- **Automatic rejection as an FO:** the 990-PF/foundation alone, with no evidence of an associated family office. (Directly per the assessment: a firm does not qualify merely because it appears in a family-office-associated source.)
- **Manual-review trigger:** a large family foundation with hints (news/site) of an associated office.

### 5. Family Holding Company
A holding company for a family's **operating businesses**.

- **Qualifies only if** it also performs a family-office function (managing the family's financial/investment wealth), with evidence.
- **Automatic rejection:** a pure operating-business holdco with no wealth-management function → §6.
- **Manual-review trigger:** holdco vs. family office ambiguous.

### Type = Undetermined
A record may qualify as a **proven family office** while its SFO/MFO type is honestly **Undetermined** (evidence establishes FO-status but not single vs. multi). This is candour, not a defect, and still counts toward the 50 — provided `fo_type_evidence` proves FO-status.

---

## 6. Non-qualifying organizations (automatic rejection)

Reject outright (route to the rejection log with reason; never ship):

- Public/listed operating companies (surface as SEC 13F noise, e.g. ticker-tagged corps).
- Banks, broker-dealers, and general-public RIAs/wealth managers with no family-office model.
- Funds raising/managing **external** capital: private equity, venture capital, hedge funds.
- Pension/benefit/union plans, ESOPs, insurance trusts.
- Religious, educational, or membership organizations with "family" in the name.
- Vendors/consultants/software serving family offices (they are suppliers, not FOs).
- Any firm whose FO-status cannot be affirmatively evidenced (fails Rule 2).

---

## Confidence policy (how `fo_type_confidence` and cell confidence are set)

- **High:** FO-status corroborated by **≥2 independent** sources of different classes (e.g., SEC filing + firm site; reputable reference + press).
- **Medium:** a single authoritative source (e.g., SEC self-description, or a reputable reference) with no contradiction.
- **Low:** weak or indirect evidence; ship only if it still clears Rule 2, and label honestly.
- Confidence **derives from evidence** (`field_confidence()` reads provenance); it is never set independently. It must fall when evidence weakens. "Confidence that never dips" is a fabrication signal.

## Source-role policy (discovery ≠ verification)

- **Discovery sources** (SEC EDGAR, IRS 990-PF, News/GDELT, Wikipedia/Wikidata) tell us a firm *might* be an FO. Discovery alone never qualifies a firm.
- **Verification sources** prove facts. **Wikipedia/Wikidata are DISCOVERY ONLY** and must never appear as a verification source (community-edited; not authoritative for a paying client). Enforced in code by the release gate.
- No single source may be both discovery and verification for the same firm unless a justification is recorded in `reviewer_notes` (flagged by `independence_warnings()`).

## Manual-review triggers (summary)
SFO vs MFO ambiguity · holdco vs FO · foundation-with-office hints · conflicting sources · resolver-flagged possible duplicates · any auto-reject that a human believes is a false reject. Manual decisions are recorded in `reviewer_notes` and remain reproducible.
