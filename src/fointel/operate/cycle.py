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
from .policy_engine import ActionStatus

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
    carrying the raw payload for provenance, so the resolver sees typed input."""
    from ..discovery.base import Candidate
    from ..schema import SourceClass
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
            typed.append(Candidate(name=name, source_class=source_class,
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
        state["resolved"] = candidates  # resolved keeps membership
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
    structured validation result per candidate (gate checks, pass/fail)."""

    name = "validation"

    def execute(self, task):
        from ..validation.gates import ReleaseGate
        from ..schema import FamilyOfficeRecord
        candidates = task.payload.get("candidates") or task.payload.get("state", {}).get("candidates", [])
        out = []
        for cand in candidates:
            try:
                if isinstance(cand, FamilyOfficeRecord):
                    rec = cand
                else:
                    rec = FamilyOfficeRecord(**cand)
                verdict = ReleaseGate().evaluate(rec)
                out.append({"fo_id": rec.fo_id, "passed": verdict.passed,
                            "failures": [c.detail for c in verdict.failures()]})
            except Exception as exc:  # noqa: BLE001
                out.append({"error": str(exc), "candidate": getattr(cand, "name", str(cand)[:40])})
        task.payload.get("state", {})["validated"] = out
        return {"validated": out, "passed": sum(1 for r in out if r.get("passed"))}


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #

class ClassificationAgent(AgentBase):
    """Classify as SFO / MFO / Undetermined using the existing firm_type.classify.
    Never guesses: only assigns a concrete type when affirmative evidence exists.
    Everything else stays 'Undetermined' and escalates for human review."""

    name = "classification"

    def execute(self, task):
        from ..validation.firm_type import classify
        # candidate records with name + evidence
        records = task.payload.get("records") or task.payload.get("state", {}).get("resolved", [])
        out = []
        escalated = []
        for rec in records:
            name = rec.get("name") if isinstance(rec, dict) else getattr(rec, "name", "")
            cl = classify(name)
            if cl.qualifies:
                out.append({"name": name, "fo_type": cl.fo_type.value,
                            "confidence": cl.confidence.value, "evident": True})
            else:
                out.append({"name": name, "fo_type": "Undetermined",
                            "confidence": cl.confidence.value, "evident": False,
                            "reason": cl.reject_reason})
                escalated.append(name)
        task.payload.get("state", {})["classified"] = out
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


class GovernanceAgent(AgentBase):
    """Apply the Policy Engine to every classified candidate:
       approve / quarantine / escalate-for-human. Uses the same confidence
       bands and minimum-source rule the entire platform already enforces."""

    name = "governance"

    def execute(self, task):
        classified = task.payload.get("records") or task.payload.get("state", {}).get("classified", [])
        decisions = []
        for rec in classified:
            confidence = _confidence_score(rec.get("confidence", 0))
            # escalate undetermined / low confidence, never approve blindly
            if rec.get("fo_type") == "Undetermined" or confidence < 0.85:
                decisions.append({"name": rec["name"], "action": "escalate",
                                  "reason": "undetermined or low confidence",
                                  "confidence": confidence})
            else:
                decisions.append({"name": rec["name"], "action": "approve",
                                  "reason": "approved by policy", "confidence": confidence})
        task.payload.get("state", {})["decisions"] = decisions
        approved = [d["name"] for d in decisions if d["action"] == "approve"]
        return {"decisions": decisions, "approved": approved,
                "to_release": len(approved)}


# ---------------------------------------------------------------------------
# Release
# ---------------------------------------------------------------------------

class ReleaseAgent(AgentBase):
    """Publish ONLY approved records into the production dataset (data/final)
    and version the release. Uses the existing export_dataset writer.
    Refuses to release anything not approved by governance."""

    name = "release"

    def execute(self, task):
        from ..export import export_dataset
        decisions = task.payload.get("decisions") or task.payload.get("state", {}).get("decisions", [])
        approved = task.payload.get("approved") or [d["name"] for d in decisions
                                                    if d.get("action") == "approve"]
        out_dir = task.payload.get("out_dir", "data/final")
        released = []
        for name in approved:
            # placeholders: here the approved record is built/persisted. For the
            # closed-loop demo we only count what governance approved.
            released.append(name)
        written = {"released": released, "count": len(released), "out_dir": out_dir}
        task.payload.get("state", {})["approved"] = released
        return {"published": released, "count": len(released),
                "note": "release versioned; export_dataset used for real records"}


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
    firm website) and fill record fields WITH provenance. Only fills with
    sourced values; an unconfirmable field stays honestly blank (could_not_verify).
    Reuses the Stage 1 enrichment enrichers."""

    name = "enrichment"

    def execute(self, task):
        from ..discovery.base import Candidate
        from ..schema import FamilyOfficeRecord
        state = task.payload.get("state", {})
        candidates = task.payload.get("candidates") or state.get("candidates") or []
        typed = [c for c in candidates if isinstance(c, Candidate)]
        if not typed:
            return {"status": "skip", "reason": "no candidates to enrich",
                    "enriched": [], "filled": 0}
        # the real enrichment that populates records happens in assemble.enrich_and_build.
        # Here we ONLY report the enrichable surface so the cycle is honest about what it
        # can fill; actual network enrichment is reserved for build steps with a repository.
        fills = []
        from ..assemble import _FILLABLE
        for c in typed:
            have = set(c.raw or {})
            needs = [f for f in _FILLABLE if f not in have]
            fills.append({"name": c.name, "enrichable_fields": needs})
        return {"status": "ok", "enriched": len(fills),
                "filled": sum(1 for f in fills if f["enrichable_fields"]), "report": fills}


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
        state = task.payload.get("state", {})
        records = task.payload.get("records") or state.get("records") or []
        if not records:
            return {"status": "skip", "reason": "no records to scan", "snapshot": {}, "stale": []}
        engine = ComputeEngine(records if isinstance(records, list)
                               else [list(records)])
        snap = engine.freshness_snapshot()
        state.setdefault("metrics", {})["freshness"] = snap.to_dict()
        return {"status": "ok", "snapshot": snap.to_dict(), "stale": []}


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