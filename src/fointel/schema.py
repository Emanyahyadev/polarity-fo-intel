"""
Data model for the Family Office intelligence dataset.

Design principles (see docs/Architecture.md and docs/DecisionLog.md):

* Rule 1 (cell-level proof): every high-value value carries provenance
  (source class + method + confidence + checked_at). A value that could not be
  verified is left blank and its field name recorded in `could_not_verify`.

* Rule 2 (firm-level proof): a record only qualifies toward the final 50 when we
  hold affirmative evidence that the firm really is a family office
  (`fo_type` in {SFO, MFO} AND `fo_type_evidence` present).

* Discovery / verification separation: `discovery_source` (how we *found* the
  firm) is kept strictly distinct from `verification_sources` (how we *proved*
  facts about it). Reusing one source for both is flagged unless documented.

* Field-level confidence: confidence lives with the evidence, per cell — it is
  derived from provenance, so it cannot be inflated independently of the basis.

* Findings govern releases: values that fail validation never sit in a delivered
  field. They are routed to the audit trail (`AuditEntry`).

The delivered file is a flattened view (`to_delivery_row()`); full cell lineage
is emitted separately (`provenance_rows()`) so the customer file stays readable
while Rule 1 remains fully auditable.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

# Bumped when the delivered schema changes; recorded in every run manifest so a
# release can be reproduced against the exact model that produced it.
SCHEMA_VERSION = "1.0.0"


class FOType(str, Enum):
    SFO = "Single-Family Office"
    MFO = "Multi-Family Office"
    UNDETERMINED = "Undetermined"  # honest label when type cannot be established


class Confidence(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


# ordering for "weakest-link" aggregation
_CONF_RANK = {Confidence.LOW: 1, Confidence.MEDIUM: 2, Confidence.HIGH: 3}


class EmailStatus(str, Enum):
    DELIVERABLE = "deliverable"
    RISKY = "risky"                  # e.g. catch-all domain; deliver with caveat
    UNDELIVERABLE = "undeliverable"  # gated OUT of delivered field -> audit
    COULD_NOT_VERIFY = "could_not_verify"


class SourceClass(str, Enum):
    # Discovery-capable source classes
    SEC_EDGAR = "SEC EDGAR (13F / SC / Form D filings)"
    IRS_990PF = "IRS 990-PF (ProPublica Nonprofit Explorer)"
    NEWS = "News / Press (GDELT)"
    DIRECTORY = "Curated directory / reference (Wikipedia, associations)"
    WEB = "Web search (Tavily)"
    # Proof / enrichment source classes (not used for discovery)
    SEC_IAPD = "SEC IAPD / Form ADV (investment-adviser registration)"
    FIRM_SITE = "Firm Website"
    LINKEDIN = "LinkedIn (public profile)"
    CROSS_SOURCE = "Cross-source corroboration"
    OTHER = "Other"


DISCOVERY_SOURCE_CLASSES = {
    SourceClass.SEC_EDGAR,
    SourceClass.SEC_IAPD,        # adviser-registry search (distinct filing system from EDGAR 13F)
    SourceClass.IRS_990PF,
    SourceClass.NEWS,
    SourceClass.DIRECTORY,
    SourceClass.WEB,
}


class Provenance(BaseModel):
    """The basis for a single value: where it came from and how it was confirmed.

    Reproducibility fields (`fetched_at`, `content_hash`, `snapshot_path`) let
    another engineer reproduce the claim from a retained snapshot months later,
    even after the live source has changed.
    """

    source_class: SourceClass
    method: str                      # e.g. "EDGAR submissions", "MX+SMTP probe", "2-source corroboration"
    checked_at: date
    source_url: Optional[str] = None
    confidence: Confidence = Confidence.MEDIUM
    note: Optional[str] = None
    # --- reproducibility ---
    fetched_at: Optional[date] = None       # when the source content was retrieved
    content_hash: Optional[str] = None       # sha256 of the retained snapshot
    snapshot_path: Optional[str] = None      # local path / archive URL of the snapshot


class SourceRef(BaseModel):
    """A source consulted to VERIFY facts about a firm (distinct from discovery)."""

    source_class: SourceClass
    verifies: str                    # what fact(s) this source was used to confirm
    accessed_at: date
    url: Optional[str] = None


class Signal(BaseModel):
    """A recent, dated activity that carries commercial value (dated signals)."""

    text: str
    source_class: SourceClass
    event_date: Optional[date] = None   # the date the activity occurred / was reported
    source_url: Optional[str] = None
    confidence: Confidence = Confidence.MEDIUM


# Fields that carry their own confidence in the delivered file. Maps a delivery
# column stem -> the record attribute it describes (for provenance lookup).
CONFIDENCE_FIELDS = [
    "name",
    "fo_type",
    "principal_name",
    "principal_email",
    "principal_phone",
    "website",
    "corporate_linkedin",
    "principal_linkedin",
    "estimated_aum",
    "investment_thesis",
    "recent_activity",
]

# Customer-visible high-value fields that MUST, when populated, carry provenance
# (Rule 1). `fo_type` is covered by `fo_type_evidence`; `signals` self-provenance
# via each Signal's own source. Everything here is enforced at release by the gate
# and by `provenance_violations()`.
HIGH_VALUE_FIELDS = [
    "name",
    "description",
    "investment_thesis",
    "estimated_aum",
    "website",
    "corporate_linkedin",
    "hq_country",
    "hq_phone",
    "principal_name",
    "principal_title",
    "principal_linkedin",
    "principal_email",
    "principal_phone",
]


class FamilyOfficeRecord(BaseModel):
    """One family office. The unit of the deliverable dataset."""

    fo_id: str

    # --- identity & classification (Rule 2 lives here) ---
    name: str
    fo_type: FOType = FOType.UNDETERMINED
    fo_type_evidence: Optional[str] = None            # classification evidence
    fo_type_confidence: Confidence = Confidence.LOW

    # --- entity attributes ---
    description: Optional[str] = None
    investment_thesis: Optional[str] = None
    investing_sectors: list[str] = Field(default_factory=list)
    estimated_aum: Optional[str] = None
    website: Optional[str] = None
    corporate_linkedin: Optional[str] = None
    hq_city: Optional[str] = None
    hq_state: Optional[str] = None
    hq_country: Optional[str] = None
    hq_phone: Optional[str] = None                    # authoritative firm main line (e.g. SEC filing)

    # --- principal / decision-maker intelligence ---
    principal_name: Optional[str] = None
    principal_title: Optional[str] = None
    principal_linkedin: Optional[str] = None
    principal_email: Optional[str] = None
    principal_email_status: Optional[EmailStatus] = None
    principal_phone: Optional[str] = None             # from authoritative source, never guessed

    # --- recent dated signals (drive commercial value) ---
    signals: list[Signal] = Field(default_factory=list)

    # --- discovery / verification separation ---
    discovery_source: SourceClass                     # how the firm was FOUND
    verification_sources: list[SourceRef] = Field(default_factory=list)  # how facts were PROVEN
    reviewer_notes: Optional[str] = None

    # --- record meta ---
    record_confidence: Confidence = Confidence.LOW    # overall, aggregated
    data_as_of: date
    could_not_verify: list[str] = Field(default_factory=list)  # honestly-blanked field names

    # --- provenance (Rule 1): field_name -> basis ---
    provenance: dict[str, Provenance] = Field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Always-true structural invariant (enforced at construction)
    # ------------------------------------------------------------------ #
    @model_validator(mode="after")
    def _no_populated_could_not_verify(self) -> "FamilyOfficeRecord":
        """A field cannot be both populated and marked 'could not verify' — that is
        a self-contradiction (we would be shipping a value we say we couldn't verify)."""
        for field in self.could_not_verify:
            if getattr(self, field, None):
                raise ValueError(
                    f"field {field!r} is populated but listed in could_not_verify"
                )
        return self

    # ------------------------------------------------------------------ #
    # Rules of proof
    # ------------------------------------------------------------------ #
    def qualifies(self) -> bool:
        """Rule 2 gate: a record counts toward the 50 only with affirmative evidence
        that the firm IS a family office. `fo_type_evidence` is that evidence. The
        SFO/MFO/Undetermined sub-type is a separate attribute — a proven FO whose
        type cannot be established is honestly labelled Undetermined and still
        qualifies (per the assessment: "if you cannot determine which type ... say
        so in the record"). See config/inclusion_standard.md."""
        return bool(self.fo_type_evidence)

    def provenance_violations(self) -> list[tuple[str, str]]:
        """Rule 1 completeness check (code, not documentation). Returns (field, reason)
        for every populated high-value field lacking provenance, plus a classified
        firm with no classification evidence. Empty list == provenance-complete.

        A field may be blank (absent) freely; if populated it must carry provenance.
        (The populated-and-could_not_verify contradiction is already impossible — it
        is rejected at construction.)"""
        violations: list[tuple[str, str]] = []
        if self.fo_type in (FOType.SFO, FOType.MFO) and not self.fo_type_evidence:
            violations.append(("fo_type", "classified as a family office without evidence"))
        for field in HIGH_VALUE_FIELDS:
            if getattr(self, field, None) and field not in self.provenance:
                violations.append((field, "populated without provenance"))
        for i, sig in enumerate(self.signals):
            # a dated signal must be traceable to a specific source document (URL), not just a
            # source class — otherwise it is an unverifiable claim.
            if not sig.source_url:
                violations.append((f"signal[{i}]", "signal without a source_url"))
        return violations

    def independence_warnings(self) -> list[str]:
        """Flag any verification source that shares the discovery source class
        without a documented justification (discovery != verification rule)."""
        warnings: list[str] = []
        for ref in self.verification_sources:
            if ref.source_class == self.discovery_source and "same-source" not in (
                self.reviewer_notes or ""
            ):
                warnings.append(
                    f"verification source {ref.source_class.value} equals discovery "
                    f"source; document justification in reviewer_notes"
                )
        return warnings

    # ------------------------------------------------------------------ #
    # Field-level confidence (derived from evidence, never set independently)
    # ------------------------------------------------------------------ #
    def field_confidence(self, field: str) -> Optional[Confidence]:
        if field == "fo_type":
            return self.fo_type_confidence
        if field == "recent_activity":
            if not self.signals:
                return None
            return min((s.confidence for s in self.signals), key=lambda c: _CONF_RANK[c])
        prov = self.provenance.get(field)
        return prov.confidence if prov else None

    def compute_record_confidence(self) -> Confidence:
        """Overall confidence = weakest link across the load-bearing fields
        (firm identity + type). Commercial fields do not raise it; missing
        evidence lowers it. This makes confidence fall naturally with evidence."""
        anchors = [self.field_confidence("name"), self.fo_type_confidence]
        present = [c for c in anchors if c is not None]
        if not present:
            return Confidence.LOW
        return min(present, key=lambda c: _CONF_RANK[c])

    # ------------------------------------------------------------------ #
    # Emission
    # ------------------------------------------------------------------ #
    def to_delivery_row(self, max_signals: int = 3) -> dict[str, object]:
        """Flat, customer-facing row. Assumes the record has already passed the gate."""
        row: dict[str, object] = {
            "fo_id": self.fo_id,
            "family_office_name": self.name,
            "fo_type": self.fo_type.value,
            "classification_evidence": self.fo_type_evidence or "",
            "description": self.description or "",
            "investment_thesis": self.investment_thesis or "",
            "investing_sectors": "; ".join(self.investing_sectors),
            "estimated_aum": self.estimated_aum or "",
            "website": self.website or "",
            "corporate_linkedin": self.corporate_linkedin or "",
            "hq_city": self.hq_city or "",
            "hq_state": self.hq_state or "",
            "hq_country": self.hq_country or "",
            "hq_phone": self.hq_phone or "",
            "principal_name": self.principal_name or "",
            "principal_title": self.principal_title or "",
            "principal_linkedin": self.principal_linkedin or "",
            "principal_email": self.principal_email or "",
            "principal_email_status": (self.principal_email_status.value
                                       if self.principal_email_status else ""),
            "principal_phone": self.principal_phone or "",
        }
        # recent signals (padded to a stable column set)
        for i in range(max_signals):
            sig = self.signals[i] if i < len(self.signals) else None
            row[f"recent_signal_{i+1}"] = sig.text if sig else ""
            row[f"recent_signal_{i+1}_date"] = (
                sig.event_date.isoformat() if sig and sig.event_date else ""
            )
            row[f"recent_signal_{i+1}_source"] = (sig.source_url or "") if sig else ""
        # field-level confidence columns
        for field in CONFIDENCE_FIELDS:
            conf = self.field_confidence(field)
            row[f"{field}_confidence"] = conf.value if conf else ""
        # discovery / verification separation + meta
        row["discovery_source"] = self.discovery_source.value
        row["verification_sources"] = "; ".join(
            f"{r.source_class.value} ({r.verifies})" for r in self.verification_sources
        )
        row["record_confidence"] = self.record_confidence.value
        row["data_as_of"] = self.data_as_of.isoformat()
        row["could_not_verify"] = "; ".join(self.could_not_verify)
        row["reviewer_notes"] = self.reviewer_notes or ""
        return row

    def provenance_rows(self) -> list[dict[str, object]]:
        """Long-format cell lineage for the provenance sheet (satisfies Rule 1 in full)."""
        return [
            {
                "fo_id": self.fo_id,
                "field": field,
                "source_class": prov.source_class.value,
                "method": prov.method,
                "source_url": prov.source_url or "",
                "confidence": prov.confidence.value,
                "checked_at": prov.checked_at.isoformat(),
                "note": prov.note or "",
            }
            for field, prov in self.provenance.items()
        ]

    def source_rows(self) -> list[dict[str, object]]:
        """Long-format verification-source references (discovery kept separate)."""
        return [
            {
                "fo_id": self.fo_id,
                "role": "verification",
                "source_class": ref.source_class.value,
                "verifies": ref.verifies,
                "url": ref.url or "",
                "accessed_at": ref.accessed_at.isoformat(),
            }
            for ref in self.verification_sources
        ] + [
            {
                "fo_id": self.fo_id,
                "role": "discovery",
                "source_class": self.discovery_source.value,
                "verifies": "",
                "url": "",
                "accessed_at": self.data_as_of.isoformat(),
            }
        ]


class AuditEntry(BaseModel):
    """A value that FAILED validation and was withheld from the delivered dataset.

    The audit trail is the proof that 'findings govern releases': we can show,
    per record, exactly what we found and chose not to ship.
    """

    fo_id: str
    field: str
    rejected_value: str
    reason: str
    source_class: SourceClass
    checked_at: date


class Candidate(BaseModel):
    """A firm surfaced by a discovery source, before enrichment or validation.

    Lives in the schema (not the discovery layer) so the data/store layer can
    persist candidates without depending on discovery. The raw payload is kept
    for full provenance back to the source.
    """

    name: str
    source_class: SourceClass          # the PRIMARY discovery source that surfaced it
    source_url: Optional[str] = None
    discovered_at: Optional[date] = None
    dedup_key: Optional[str] = None    # normalised name (fallback only; identifiers preferred)
    # Strong identifiers used by entity resolution (never merge without evidence):
    identifiers: dict = Field(default_factory=dict)   # {"cik": .., "ein": .., "qid": .., "domain": ..}
    # All discovery sources that surfaced this firm (multi-source discovery is a signal):
    discovery_sources: list[str] = Field(default_factory=list)
    raw: dict = Field(default_factory=dict)     # source-specific payload
    hints: dict = Field(default_factory=dict)   # cheap hints (city, principal, ...)
