"""
Autonomous Operating Cycle agents (Stage 2).

The full business loop implemented as deterministic AI Employees on top of the
existing Orchestrator + Policy Engine:

    Scheduler Wake -> Engineering Judgment -> Discovery -> Entity Resolution
    -> Validation -> Classification -> Governance -> Release -> Logging -> Sleep

Design contract (per Eman's decisions):
  * Each agent OWNS one responsibility, knows what it may never do, and escalates
    instead of guessing.
  * No model inside control flow. The Policy Engine is the single authority on
    whether any action may run autonomously (Tier 1) or must escalate (Tier 2)
    or is refused (Tier 3).
  * Every agent reads/writes a shared cycle `state` dict (threaded through task
    payloads) so a full run is deterministic and replayable.
  * Every step emits structured logs through the orchestrator trace.

Stage 1 discovery / entity-resolution / classification / release services are
REUSED (harvest, EntityResolver, firm_type.classify, ReleaseGate,
export_dataset), never duplicated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .orchestrator import Orchestrator, AgentBase, Task, RunTrace
from .policy_engine import ActionStatus, PolicyEngineFactory
from ..schema import SourceClass

# --------------------------------------------------------------------------- #
# Cycle state
# --------------------------------------------------------------------------- #

@dataclass
class CycleState:
    """The working context threaded through one operating cycle."""
    candidates: list = field(default_factory=list)      # raw candidates from discovery
    resolved: list = field(default_factory=list)        # after entity resolution
    validated: list = field(default_factory=list)       # validation results
    classified: list = field(default_factory=list)      # with fo_type assigned
    decisions: list = field(default_factory=list)       # governance decisions
    approved: list = field(default_factory=list)        # released records
    quarantined: list = field(default_factory=list)
    escalated: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


# --------------------------------------------------------------------------- #
# Engineering Judgment — Chief Engineer
# --------------------------------------------------------------------------- #

class EngineeringAgent(AgentBase):
    """Chief Engineer. Inspects system state and dispatches this cycle's work:
    decide what runs, in what order, and pause when a required precondition
    (e.g. an empty candidate pool) would make a later step unsafe or vacuous."""

    name = "engineering"

    def execute(self, task):
        state = task.payload.get("state", {})
        # Build the ordered plan for this cycle, each scaled by available input.
        # A stage with no input is SKIPPED, never run against nothing.
        plan = [
            "scheduler", "engineering", "discovery", "entity",
            "validation", "classification", "governance", "release", "logging",
        ]
        pausing = []
        if not state.get("candidates"):
            pausing.append("no candidates to process -> validation/classification/governance skip")
        return {
            "plan": plan,
            "paused_stages": pausing,
            "priority": "process_candidate_pool",
            "decision": "proceed" if not pausing else "pause_unsafe_stages",
        }


# --------------------------------------------------------------------------- #
# Discovery — provided by the orchestrator's DiscoveryAgent (reuses harvest).
# The cycle forwards to it; no duplicate employee here.
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Entity Resolution
# --------------------------------------------------------------------------- #

def _as_candidates(candidates) -> list:
    """Coerce cycle candidates (typed `Candidate` or raw dicts) to `Candidate`.
    Never guesses: a raw dict with no usable identity becomes a bare Candidate
    carrying the raw payload for provenance, so the resolver sees typed input.
    Full-fidelity re-typing: when a candidate came FROM the discovery harvest its
    identifiers/source_url/dedup_key round-trip so downstream enrichment can still
    resolve CIK/CRD/qid — never loses a strong identifier."""
    from ..schema import Candidate, SourceClass
    typed = []
    for cand in candidates or []:
        if isinstance(cand, Candidate):
            typed.append(cand)
        elif isinstance(cand, dict):
            name = str(cand.get("name") or cand.get("record_name") or "").strip()
            source = cand.get("source") or cand.get("source_class") or "Other"
            try:
                source_class = SourceClass(source) if isinstance(source, str) else SourceClass.OTHER
            except ValueError:
                source_class = SourceClass.OTHER
            typed.append(Candidate(
                name=name, source_class=source_class,
                source_url=cand.get("source_url"),
                discovered_at=cand.get("discovered_at"),
                dedup_key=cand.get("dedup_key"),
                identifiers=cand.get("identifiers") or {},
                discovery_sources=cand.get("discovery_sources") or [],
                raw=cand, hints=cand.get("hints", {})))
        # skip anything else; never guess a candidate from an invalid shape
    return typed


def _as_typed_records(records) -> list:
    """Coerce raw dicts to `FamilyOfficeRecord` for the cycle's typed expectations."""
    from ..schema import FamilyOfficeRecord
    out = []
    for rec in records or []:
        if isinstance(rec, FamilyOfficeRecord):
            out.append(rec)
        elif isinstance(rec, dict):
            try:
                out.append(FamilyOfficeRecord(**rec))
            except Exception:  # noqa: BLE001 — skip records that can't be typed
                continue
    return out


class EntityResolutionAgent(AgentBase):
    """Normalize names, resolve aliases/identifiers, merge obvious duplicates.
    Uses the existing EntityResolver (evidence-first, never merges without
    identifier/name+geo evidence). Emits every MergeDecision to logs."""

    name = "entity"

    def execute(self, task):
        from ..entity_resolution import EntityResolver
        candidates = task.payload.get("candidates") or task.payload.get("state", {}).get("candidates", [])
        typed = _as_candidates(candidates)
        resolver = EntityResolver()
        resolved, decisions = resolver.resolve(typed)
        state = task.payload.get("state", {})
        state["resolved"] = [c.model_dump(mode="json") for c in resolved]
        return {
            "resolved": len(resolved),
            "merges": sum(1 for d in decisions if d.action == "merge"),
            "possible_duplicates": sum(1 for d in decisions
                                       if d.action == "possible_duplicate_kept_distinct"),
            "decisions": [d.model_dump() for d in decisions],
        }


# --------------------------------------------------------------------------- #
# Validation — apply the release gates + policy engine
# --------------------------------------------------------------------------- #

class ValidationAgent(AgentBase):
    """Verify candidate evidence against the existing ReleaseGate. Produces a
    structured validation result per record (gate checks, pass/fail). Prefers the
    enriched `records` built by the enrichment stage; falls back to raw candidates
    so driving the agent directly stays honest about missing gates."""

    name = "validation"

    def execute(self, task):
        from ..validation.gates import ReleaseGate
        from ..schema import FamilyOfficeRecord
        state = task.payload.get("state", {})
        records = (task.payload.get("records") or state.get("records")
                   or state.get("candidates") or task.payload.get("candidates") or [])
        out = []
        for cand in records:
            try:
                if isinstance(cand, FamilyOfficeRecord):
                    rec = cand
                else:
                    rec = FamilyOfficeRecord(**cand)
                verdict = ReleaseGate().evaluate(rec)
                out.append({"fo_id": rec.fo_id, "name": rec.name, "passed": verdict.passed,
                            "failures": [c.detail for c in verdict.failures()]})
            except Exception as exc:  # noqa: BLE001
                out.append({"error": str(exc),
                            "candidate": getattr(cand, "name", str(cand)[:40])})
        state["validated"] = [o for o in out if not o.get("error")]
        return {"validated": out,
                "passed": sum(1 for r in out if r.get("passed")),
                "failures": sum(1 for r in out if r.get("failures"))}


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #

class ClassificationAgent(AgentBase):
    """Assign the SFO / MFO / Undetermined label per record.
    Never guesses: records built by the enrichment stage carry an evidence-bound
    classification (`fo_type` + `fo_type_evidence` from the firm-type classifier
    run over the authoritative facts). A type claimed WITHOUT evidence is treated
    as Undetermined and escalates; when driven on raw candidates (no built records)
    it falls back to the existing firm_type.classify over the name and escalates
    everything without affirmative evidence."""

    name = "classification"

    def execute(self, task):
        from ..validation.firm_type import classify
        state = task.payload.get("state", {})
        records = (task.payload.get("records") or state.get("records")
                   or state.get("resolved") or state.get("candidates") or [])
        out = []
        escalated = []
        for rec in records:
            name = rec.get("name") if isinstance(rec, dict) else getattr(rec, "name", "")
            # Built/enriched record path: surface the evidence-bound classification
            # the enrichment stage already produced.
            if isinstance(rec, dict) and rec.get("fo_type"):
                claimed = rec.get("fo_type")
                evidence = rec.get("fo_type_evidence")
                confidence = rec.get("fo_type_confidence") or rec.get("record_confidence") or "Low"
                if claimed != "Undetermined" and evidence:
                    out.append({"name": name, "fo_id": rec.get("fo_id"),
                                "fo_type": claimed, "confidence": confidence,
                                "evident": True})
                else:
                    out.append({"name": name, "fo_id": rec.get("fo_id"),
                                "fo_type": "Undetermined", "confidence": confidence,
                                "evident": False,
                                "reason": evidence or "no affirmative classification evidence"})
                    escalated.append(name)
                continue
            # Raw-candidate path (unbuilt): never assign a type from the name alone —
            # the name-only classifier rejects without evidence, so this escalates.
            cl = classify(name)
            if cl.qualifies:
                out.append({"name": name, "fo_type": cl.fo_type.value,
                            "confidence": cl.confidence.value, "evident": True})
            else:
                out.append({"name": name, "fo_type": "Undetermined",
                            "confidence": cl.confidence.value, "evident": False,
                            "reason": cl.reject_reason})
                escalated.append(name)
        state["classified"] = out
        state["escalated"] = escalated or state.get("escalated", [])
        return {"classified": out, "escalated_uncertain": escalated,
                "assigned": len(out) - len(escalated)}


# --------------------------------------------------------------------------- #
# Governance — apply policy engine
# --------------------------------------------------------------------------- #

def _confidence_score(value) -> float:
    """Normalise a confidence to a 0..1 score for the governance policy gate.

    Accepts the numeric forms already used by the policy engine (0..1 or 0..100)
    AND the qualitative `Confidence` label emitted by `firm_type.classify`
    (High / Medium / Low). The label never exceeds the classifier's evidence:
    High = 2+ authoritative sources (auto-release band), Medium = 1 authoritative
    source (governance-review band), Low = no affirmative evidence (quarantine).
    """
    from ..validation.firm_type import Confidence
    if isinstance(value, Confidence):
        value = value.value
    if isinstance(value, str):
        mapping = {Confidence.HIGH.value: 0.90, Confidence.MEDIUM.value: 0.80,
                   Confidence.LOW.value: 0.30}
        if value.strip().lower() in ("high", "medium", "low", "auto"):
            return mapping.get(value.strip().title(), 0.30)
        try:
            return float(value)
        except (TypeError, ValueError):
            # never fabricate a number from an unknown label; treat as no evidence
            return 0.30
    confidence = float(value or 0)
    return confidence / 100.0 if confidence > 1.0 else confidence


def _authoritative_source_count(rec) -> int:
    """Authoritative verification sources on a built record (dict or object).
    Directory-class sources can never verify, so they never count toward the
    minimum; anything unusable is treated as absent (never invented)."""
    from ..validation.gates import DISCOVERY_ONLY

    raw = (rec.get("verification_sources") if isinstance(rec, dict)
           else getattr(rec, "verification_sources", [])) or []
    n = 0
    for s in raw:
        sc = (s.get("source_class") if isinstance(s, dict)
              else getattr(s, "source_class", None))
        if sc is None:
            continue
        try:
            cls = sc if not isinstance(sc, str) else SourceClass(sc)
        except (TypeError, ValueError):
            continue
        if cls not in DISCOVERY_ONLY:
            n += 1
    return n


class GovernanceAgent(AgentBase):
    """Apply the Policy Engine to every classified candidate:
       approve / quarantine / escalate-for-human. Uses the same confidence
       bands and minimum-source rule the entire platform already enforces —
       a record is NOT approvable unless it carries >= 2 AUTHORITATIVE
       verification sources on the BUILT record (SEC/IAPD/13F/website evidence,
       never a directory listing) plus the classification confidence band."""

    name = "governance"

    def execute(self, task):
        state = task.payload.get("state", {})
        classified = task.payload.get("classified") or state.get("classified", [])
        pool = task.payload.get("records") or state.get("records") or []
        by_id = {c.get("fo_id"): c for c in pool if isinstance(c, dict) and c.get("fo_id")}
        by_name = {c.get("name"): c for c in pool if isinstance(c, dict) and c.get("name")}
        decisions = []
        for rec in classified:
            confidence = _confidence_score(rec.get("confidence", 0))
            name = rec.get("name")
            fo_id = rec.get("fo_id")
            built = by_id.get(fo_id) or by_name.get(name) or {}
            sources = _authoritative_source_count(built)
            # escalate undetermined / low confidence / under-sourced, never approve blindly
            if rec.get("fo_type") == "Undetermined" or confidence < 0.85 \
                    or not rec.get("evident", True) or sources < 2:
                reasons = []
                if sources < 2:
                    reasons.append(f"insufficient independent sources ({sources} "
                                   f"authoritative; minimum 2)")
                if rec.get("fo_type") == "Undetermined" or not rec.get("evident", True):
                    reasons.append("undetermined or no affirmative evidence")
                if confidence < 0.85:
                    reasons.append("low confidence")
                decisions.append({"name": name, "fo_id": fo_id, "action": "escalate",
                                  "reason": "; ".join(reasons) or "governance review",
                                  "confidence": confidence,
                                  "n_sources": sources})
            else:
                decisions.append({"name": name, "fo_id": fo_id, "action": "approve",
                                  "reason": "approved by policy",
                                  "confidence": confidence,
                                  "n_sources": sources})
        # Contact governance (Correction 7 / Stage 2 Target 3): a named-person contact
        # is a SEPARATE authority decision from the firm-level publish decision — a
        # firm record can be approved while its contact route is still escalated or
        # refused. This is the first real wiring of PolicyEngine.contact_review into
        # control flow (previously defined but never invoked). Release enforces the
        # result by stripping any contact not explicitly authorized here.
        contact_decisions = []
        try:
            policy = PolicyEngineFactory.load()
        except Exception:
            policy = None
        if policy is not None:
            for rec in classified:
                fo_id = rec.get("fo_id")
                name = rec.get("name")
                built = by_id.get(fo_id) or by_name.get(name) or {}
                email = built.get("principal_email")
                person = built.get("principal_name")
                if not email:
                    continue
                status = built.get("principal_email_status") or "risky"
                # a name-matched firm-site email starts at MEDIUM confidence — real
                # but not SMTP-deliverability-verified (no verifier is wired yet).
                conf = 0.75 if status == "risky" else 0.95
                decision = policy.contact_review(
                    person=person or "", email=email, email_type="corporate",
                    source_type="firm_site", confidence=conf)
                contact_decisions.append({"fo_id": fo_id, "name": name,
                                          "contact_action": decision.status,
                                          "reason": decision.reason})
        state["decisions"] = decisions
        state["contact_decisions"] = contact_decisions
        approved = [d["name"] for d in decisions if d["action"] == "approve"]
        return {"decisions": decisions, "approved": approved,
                "to_release": len(approved), "contact_decisions": contact_decisions}


# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------

class ReleaseAgent(AgentBase):
    """Publish ONLY approved records into the production dataset (data/final)
    and version the release. Uses the existing export_dataset writer.

    The store (`out_dir/records.json`) is the lossless canonical source of truth;
    the CSV/XLSX are exported from it. The merge NEVER drops an existing curated
    record — new approved records are added by `fo_id`, existing ones win. Nothing
    is written unless governance approved at least one NEW record this window
    (empty windows stay a clean no-op)."""

    name = "release"

    def execute(self, task):
        import json
        from pathlib import Path
        from ..export import export_dataset
        from ..rag.load import load_records_from_store
        from ..schema import AuditEntry, FamilyOfficeRecord
        from ..validation.gates import ReleaseGate
        state = task.payload.get("state", {})
        decisions = task.payload.get("decisions") or state.get("decisions", [])
        approved_ids = {d.get("fo_id") for d in decisions
                        if d.get("action") == "approve" and d.get("fo_id")}
        approved_names = {d.get("name") for d in decisions if d.get("action") == "approve"}
        # a firm record may ship while its named-person contact stays gated: only a
        # Tier-1 "autonomous" contact_review decision authorizes principal_email/
        # principal_email_status/principal_linkedin to leave with the record.
        contact_decisions = task.payload.get("contact_decisions") or state.get(
            "contact_decisions", [])
        not_authorized_ids = {d.get("fo_id") for d in contact_decisions
                              if d.get("contact_action") != "autonomous" and d.get("fo_id")}
        out_dir = task.payload.get("out_dir") or state.get("out_dir") or "data/final"
        out = Path(out_dir)
        store_path = out / "records.json"

        # persisted audit trail feeds the export's Audit sheet (findings govern releases)
        # and lets the release gate re-assert no rejected value is ever shipped (G9).
        audit: list[AuditEntry] = []
        audit_path = out / "audit.json"
        if audit_path.exists():
            try:
                audit = [AuditEntry.model_validate(a)
                         for a in json.loads(audit_path.read_text(encoding="utf-8"))]
            except Exception:  # noqa: BLE001
                audit = []
        audit_by_fo: dict[str, list[AuditEntry]] = {}
        for a in audit:
            audit_by_fo.setdefault(a.fo_id, []).append(a)
        gate = ReleaseGate(audit_by_fo=audit_by_fo)

        # assemble the approved records this window from the built pool
        approved_records = []
        pool = state.get("records") or task.payload.get("records") or []
        for rec in pool:
            rid = rec.get("fo_id") if isinstance(rec, dict) else getattr(rec, "fo_id", None)
            rname = rec.get("name") if isinstance(rec, dict) else getattr(rec, "name", "")
            if (rid and rid in approved_ids) or (rid is None and rname in approved_names):
                if rid in not_authorized_ids:
                    # governance did not clear this contact for release (escalate/refuse):
                    # ship the firm record, withhold the un-cleared named-person route.
                    if isinstance(rec, dict):
                        rec = dict(rec)
                        rec["principal_email"] = None
                        rec["principal_email_status"] = None
                        rec["principal_linkedin"] = None
                        cnv = list(rec.get("could_not_verify") or [])
                        for f in ("principal_email", "principal_linkedin"):
                            if f not in cnv:
                                cnv.append(f)
                        rec["could_not_verify"] = cnv
                approved_records.append(rec)

        if not approved_records:
            state["approved"] = state.get("approved", [])
            return {"published": [], "count": 0,
                    "note": "no approved records this window; nothing written",
                    "store_file": str(store_path)}

        # canonical store: existing records win by fo_id, new approved are added
        existing: list[FamilyOfficeRecord] = []
        if store_path.exists():
            try:
                existing = load_records_from_store(str(store_path))
            except Exception as exc:  # noqa: BLE001 — never delete on a bad read
                state.setdefault("errors", []).append(f"release store read: {exc}")

        have_ids = {r.fo_id for r in existing}
        added: list[FamilyOfficeRecord] = []
        withheld: list[dict] = []
        for rec in approved_records:
            rdict = rec if isinstance(rec, dict) else rec.model_dump(mode="json")
            try:
                obj = FamilyOfficeRecord.model_validate(rdict)
            except Exception:  # noqa: BLE001 — a record that won't round-trip is not shipped
                continue
            if obj.fo_id in have_ids:
                continue  # already released (curated or a previous window): existing wins
            # RE-ASSERT the release gates at the release boundary: governance
            # approval alone never ships — only gate-passing records enter the store.
            outcome = gate.evaluate(obj)
            if not outcome.passed:
                withheld.append({"fo_id": obj.fo_id,
                                 "failed": [c.name for c in outcome.failures()]})
                state.setdefault("errors", []).append(
                    f"release withheld {obj.fo_id} on gate re-assertion: "
                    f"{', '.join(c.name for c in outcome.failures())}")
                continue
            added.append(obj)

        if not added:
            state["approved"] = state.get("approved", [])
            return {"published": [], "count": 0, "withheld": withheld,
                    "note": ("approved records already in store or blocked by gate "
                             "re-assertion; nothing new to publish"),
                    "store_file": str(store_path)}

        merged = existing + added
        out.mkdir(parents=True, exist_ok=True)
        store_path.write_text(
            json.dumps([r.model_dump(mode="json") for r in merged], indent=2,
                       ensure_ascii=False), encoding="utf-8")

        # persisted audit trail feeds the export's Audit sheet (findings govern releases)
        res = export_dataset(merged, audit=audit, out_dir=out_dir)
        released_names = [r.name for r in added]
        state["approved"] = released_names
        state.setdefault("metrics", {})["release"] = {
            "published": len(added), "store_total": len(merged),
            "withheld_on_gates": len(withheld), **res}
        return {"published": released_names, "count": len(added),
                "store_file": str(store_path), "store_total": len(merged),
                "withheld": withheld,
                "note": f"merged {len(added)} new records; {len(merged)} total in store"}


# --------------------------------------------------------------------------- #
# Duplicate Detection — post-enrichment dedup (owns one responsibility)
# --------------------------------------------------------------------------- #

class DuplicateDetectionAgent(AgentBase):
    """Post-enrichment entity resolution. Runs the existing `dedupe_records`
    pass (shared-domain / name+geo merges) over the enriched pool and EMITS every
    merge decision. Ambiguous duplicates must NEVER be merged — they stay distinct
    and are flagged for review. Reuses `assemble.dedupe_records`; no logic here."""

    name = "duplicate"

    def execute(self, task):
        from ..assemble import dedupe_records
        from ..schema import FamilyOfficeRecord
        state = task.payload.get("state", {})
        records = task.payload.get("records") or state.get("records") \
            or state.get("resolved") or []
        typed = [r for r in records if isinstance(r, FamilyOfficeRecord)]
        if not typed:
            return {"status": "skip", "reason": "no enriched records to dedupe",
                    "merges": [], "possible_duplicates": [], "decisions": []}
        kept, decisions = dedupe_records(typed)
        state.setdefault("decisions", []).extend(
            {"name": d["kept"], "action": "merge",
             "basis": d.get("basis", ""),
             "merged_out": d["merged_out"]} for d in decisions)
        return {"kept": len(kept), "merges": len(decisions),
                "decisions": [d for d in decisions],
                "possible_duplicates": [d for d in decisions if "ambiguous" in d.get("basis", "")]}


# --------------------------------------------------------------------------- #
# Enrichment — fetch + fill fields from authoritative sources
# --------------------------------------------------------------------------- #

class EnrichmentAgent(AgentBase):
    """Fetch authoritative facts for each candidate (SEC EDGAR, IAPD/ADV, 13F,
    firm website) and fill record fields WITH provenance. Then reports the
    enrichable surface honestly. Reuses the Stage 1 enrichers + `enrich_and_build`,
    so every populated cell carries provenance and only qualifying, classified
    records enter the cycle's `records` channel for validation/gate/release."""

    name = "enrichment"

    def execute(self, task):
        from datetime import date
        from ..assemble import enrich_and_build
        state = task.payload.get("state", {})
        candidates = (task.payload.get("candidates") or state.get("resolved")
                      or state.get("candidates") or [])
        typed = _as_candidates(candidates)
        if not typed:
            return {"status": "skip", "reason": "no candidates to enrich",
                    "enriched": 0, "filled": 0, "report": {}}
        # optional build cap: bound the first live runs so a large harvest does not
        # stall the window with per-candidate SEC/IAPD/13F/website fetches ("max_build"
        # may arrive via task payload or the cycle state inputs).
        max_build = task.payload.get("max_build") or state.get("max_build")
        if max_build:
            typed = typed[: int(max_build)]
        records, report = enrich_and_build(typed, as_of=date.today())
        state["records"] = [r.model_dump(mode="json") for r in records]
        # "filled" = records that cleared classification with at least one
        # independent verification source (evidence-backed, never invented).
        filled = sum(1 for r in records if len(r.verification_sources) >= 1)
        return {"status": "ok", "enriched": len(records), "filled": filled,
                "cap_applied": int(max_build) if max_build else None,
                "report": report}


# --------------------------------------------------------------------------- #
# Freshness — detect stale / refresh / record in report
# --------------------------------------------------------------------------- #

class FreshnessAgent(AgentBase):
    """Freshness gate over the release-authorized dataset. Detects how current
    each record's `data_as_of` is against today and flags stale / inactive records
    for governance. Deterministic (ComputeEngine.freshness_snapshot); no model."""

    name = "freshness"

    def execute(self, task):
        from ..compute import ComputeEngine
        from .freshness_trust import run_cross_cycle_check
        state = task.payload.get("state", {})
        records = task.payload.get("records") or state.get("records") or []
        typed = _as_typed_records(records)
        if not typed:
            return {"status": "skip", "reason": "no records to scan", "snapshot": {}, "stale": []}
        engine = ComputeEngine(typed)
        snap = engine.freshness_snapshot()
        state.setdefault("metrics", {})["freshness"] = snap.to_dict()
        # Cross-run trust check: compares the FULL current production store
        # against the snapshot the PREVIOUS cycle persisted, on trust-bearing
        # fields only, so a cycle that only touches a handful of records still
        # has power to catch a real diff anywhere in the released set. A real
        # diff (classification flip, confidence drop, contact field
        # change/disappearance) is evidence-based staleness, not a day-count.
        try:
            from ..rag.load import load_records_from_store
            full_store = load_records_from_store()
            cross_input = [r.model_dump(mode="json") for r in full_store]
        except Exception:
            cross_input = [r.model_dump(mode="json") for r in typed]
        cross = run_cross_cycle_check(cross_input)
        state.setdefault("metrics", {})["cross_run_trust"] = cross
        return {"status": "ok", "snapshot": snap.to_dict(), "stale": cross["stale"],
                "cross_run_trust": cross}


# --------------------------------------------------------------------------- #
# Monitoring — emit a health snapshot for the run
# --------------------------------------------------------------------------- #

class MonitoringAgent(AgentBase):
    """Health + coverage snapshot for the run: counts of each threaded list, the
    run trace size, and any errors/escalations. Passive observer; never decides.
    Self-contained: takes no dependency on the caller's trace so the identical
    snapshot works under the Orchestrator AND the LangGraph adapter path."""

    name = "monitoring"

    def execute(self, task):
        state = task.payload.get("state", {})
        snap = {
            "candidates": len(state.get("candidates", [])),
            "resolved": len(state.get("resolved", [])),
            "records": len(state.get("records", [])),
            "approved": len(state.get("approved", [])),
            "quarantined": len(state.get("quarantined", [])),
            "escalated": len(state.get("escalated", [])),
            "errors": len(state.get("errors", [])),
        }
        if task.payload.get("emit"):
            o = task.orchestrator
            o.trace.emit({"event": "monitoring_snapshot", "snapshot": snap,
                          "run_id": o.run_id})
        return {"status": "ok", "snapshot": snap}


# --------------------------------------------------------------------------- #
# Embedding Update — refresh the RAG vector index after a release
# --------------------------------------------------------------------------- #

class EmbeddingUpdateAgent(AgentBase):
    """After governance releases approved records, refresh the retrieval corpus:
    re-embed the release-authorized dataset so the live RAG answers from today's
    dataset, not the frozen image vectors. Runs only when a release published a
    different record count than the index already serves (idempotent)."""

    name = "embedding"

    def execute(self, task):
        state = task.payload.get("state", {})
        out_dir = task.payload.get("out_dir", "data/final")
        release = len(state.get("approved", []))
        if release == 0:
            return {"status": "skip", "reason": "no new approved records; no index refresh",
                    "updated": False}
        from ..rag import load as rag_load
        csv = f"{out_dir}/family_offices.csv"
        try:
            records = rag_load.load_records_from_csv(csv)
        except FileNotFoundError:
            return {"status": "skip", "reason": f"release csv not found at {csv}",
                    "updated": False}
        from ..rag.index import precompute_and_save
        shapes = precompute_and_save(records)
        state.setdefault("metrics", {})["embedding"] = {
            "updated": True, "records": len(records),
            "docs": shapes[0], "focus": shapes[1]}
        return {"status": "ok", "updated": True, "records": len(records)}


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #

def register_cycle_agents(orchestrator: Orchestrator) -> None:
    """Register the full operating-cycle agent roster on an already-configured
    orchestrator. Idempotent: existing agents are left untouched."""
    roster = {
        "engineering": EngineeringAgent,
        "entity": EntityResolutionAgent,
        "validation": ValidationAgent,
        "classification": ClassificationAgent,
        "governance": GovernanceAgent,
        "release": ReleaseAgent,
        "duplicate": DuplicateDetectionAgent,
        "enrichment": EnrichmentAgent,
        "freshness": FreshnessAgent,
        "monitoring": MonitoringAgent,
        "embedding": EmbeddingUpdateAgent,
    }
    for name, cls in roster.items():
        if name not in orchestrator.agents:
            orchestrator.register(cls(orchestrator))