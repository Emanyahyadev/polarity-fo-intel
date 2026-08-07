"""
Policy Engine (Phase 1 Step 5) — where engineering judgment lives as CODE.

Loads Eman's policies from policies/authority.json + policies/contacts.json and
decides, for any proposed action, whether the system may do it autonomously
(Tier 1), must escalate (Tier 2), or must refuse (Tier 3), plus the
confidence-based release/retention authority.

This is the enforcement layer: it is invoked in control flow BEFORE any action is
taken, and it produces an auditable AuthorityDecision for every proposal. It never
acts on its own judgment — it only applies the policies Eman wrote.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

POLICIES_DIR = Path(__file__).resolve().parents[3] / "policies"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ActionStatus:
    AUTONOMOUS = "autonomous"
    ESCALATE = "escalate"
    REFUSE = "refuse"


@dataclass
class AuthorityDecision:
    action: str
    status: str                 # ActionStatus.*
    tier: int                   # 1 | 2 | 3
    reason: str
    policy: str = ""            # which policy rule decided it
    at: str = field(default_factory=_now)
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def is_autonomous(self) -> bool:
        return self.status == ActionStatus.AUTONOMOUS


@dataclass
class ReviewItem:
    """A record/decision routed to the human review queue (Eman's seat)."""
    id: str
    reason: str
    suggested_action: str
    status: str = "pending"
    at: str = field(default_factory=_now)
    context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class HumanReviewQueue:
    """The automatic queue for anything that needs Eman's judgment."""

    def __init__(self) -> None:
        self.items: list[ReviewItem] = []

    def add(self, item_id: str, reason: str, suggested_action: str,
            context: dict | None = None) -> ReviewItem:
        it = ReviewItem(id=item_id, reason=reason, suggested_action=suggested_action,
                        context=context or {})
        self.items.append(it)
        return it

    def pending(self) -> list[ReviewItem]:
        return [i for i in self.items if i.status == "pending"]

    def all(self) -> list[dict]:
        return [i.to_dict() for i in self.items]

    def resolve(self, item_id: str, decision: str, decided_by: str, note: str = "") -> None:
        """Record Eman's (or a human's) decision on a queued item."""
        for i in self.items:
            if i.id == item_id:
                i.status = decision
                i.context["decided_by"] = decided_by
                i.context["decision_note"] = note
                i.context["decided_at"] = _now()
                return
        raise KeyError(f"no review item {item_id!r}")


class PolicyEngine:
    """Applies Eman's authority matrix + confidence authority to every proposal."""

    def __init__(self, policies_dir: Path = POLICIES_DIR) -> None:
        self.policies_dir = Path(policies_dir)
        with open(self.policies_dir / "authority.json", encoding="utf-8") as fh:
            self.authority = json.load(fh)
        with open(self.policies_dir / "contacts.json", encoding="utf-8") as fh:
            self.contacts = json.load(fh)
        self.queue = HumanReviewQueue()

    # ------------------------------------------------------------------ #
    # Tier decision
    # ------------------------------------------------------------------ #
    def decide(self, action: str, payload: dict | None = None) -> AuthorityDecision:
        """Decide the authority tier for a proposed action (Tier 1/2/3)."""
        payload = payload or {}
        # Tier 3 first: hard refusals override everything.
        never = self.authority["authority_matrix"]["tier_3_refuse"]["never"]
        tier1 = self.authority["authority_matrix"]["tier_1_autonomous"]["actions"]

        for banned in never:
            if banned in action:
                return AuthorityDecision(
                    action=action, status=ActionStatus.REFUSE, tier=3,
                    reason=f"Tier 3 refusal: {banned}", policy="tier_3_refuse",
                    payload=payload)

        for name, status in tier1.items():
            if action == name:
                if status == "autonomous":
                    return AuthorityDecision(
                        action=action, status=ActionStatus.AUTONOMOUS, tier=1,
                        reason=f"Tier 1 autonomous action ({name})",
                        policy="tier_1_autonomous", payload=payload)
                if status == "escalate":
                    return self._escalate(action, payload, f"ambiguous action {name}")

        # Everything not in Tier 1 and not refused is escalated by default —
        # the agent proposes, governance/human decides. Never guesses.
        return self._escalate(action, payload,
                              "not an explicitly autonomous action; escalating by default")

    def _escalate(self, action: str, payload: dict, reason: str) -> AuthorityDecision:
        return AuthorityDecision(
            action=action, status=ActionStatus.ESCALATE, tier=2,
            reason=reason, policy="tier_2_escalate", payload=payload)

    # ------------------------------------------------------------------ #
    # Confidence-based authority (release/retention)
    # ------------------------------------------------------------------ #
    def confidence_authority(self, confidence: float) -> str:
        """Map a numeric confidence to the release action (Eman's table)."""
        for band in self.authority["confidence_authority"]:
            lo = band["min"]
            hi = band.get("max", 1.01)
            if lo <= confidence < hi:
                return band["action"]
        return "quarantine"

    def may_publish(self, confidence: float, n_sources: int) -> AuthorityDecision:
        """Governance gate for publish_record (Eman's policy engine)."""
        gov = self.authority["governance_policy_engine"]["publish_record"]
        if not gov["require_validation"]:
            return self._refuse("publish_record", "validation disabled")
        if n_sources < gov["minimum_sources"]:
            return self._refuse("publish_record",
                                f"only {n_sources} source(s); minimum {gov['minimum_sources']}")
        if confidence < gov["minimum_confidence"]:
            return self._escalate("publish_record",
                                  {"confidence": confidence, "n_sources": n_sources},
                                  f"confidence {confidence:.2f} < {gov['minimum_confidence']}; "
                                  "governance review")
        action = self.confidence_authority(confidence)
        if action in ("auto_release", "auto_release_medium"):
            return AuthorityDecision(
                action="publish_record", status=ActionStatus.AUTONOMOUS, tier=1,
                reason=f"confidence {confidence:.2f} -> {action}",
                policy="governance_policy_engine.publish_record",
                payload={"confidence": confidence, "n_sources": n_sources})
        if action == "hold_governance_review":
            return self._escalate("publish_record",
                                  {"confidence": confidence, "n_sources": n_sources},
                                  f"confidence {confidence:.2f} in gray zone")
        return self._refuse("publish_record",
                            f"confidence {confidence:.2f} < 0.70 -> quarantine")

    # ------------------------------------------------------------------ #
    # Contact standard enforcement (Correction 7)
    # ------------------------------------------------------------------ #
    def contact_review(self, person: str, email: str, email_type: str,
                       source_type: str, confidence: float) -> AuthorityDecision:
        """Apply Eman's contact governance rules: auto-publish / human-review / reject.

        A generic mailbox (info@/contact@/hello@) or a personal email NEVER counts
        as a named-person route. This is enforced in control flow, not prose.
        """
        generic = email.split("@")[0].strip().lower() in ("info", "contact", "hello",
                                                          "office", "admin", "noreply")
        if not person or not person.strip():
            return self._refuse("contact.publish",
                                "no named person; generic mailboxes are not routes")
        if generic:
            return self._refuse("contact.publish",
                                f"generic mailbox {email!r} is not a named-person route")
        if email_type != "corporate":
            return self._refuse("contact.publish",
                                f"non-corporate email type {email_type!r} does not qualify")
        gov = self.contacts["contact_standard"]["governance_rules"]
        if source_type in ("vendor", "hunter.io", "apollo", "rocketreach", "contactout", "signalhire"):
            return self._escalate("contact.publish",
                                  {"person": person, "source_type": source_type},
                                  "vendor-only evidence; must be corroborated before promotion")
        if confidence >= 0.90:
            return AuthorityDecision(
                action="contact.publish", status=ActionStatus.AUTONOMOUS, tier=1,
                reason=f"named person + corporate email + confidence {confidence:.2f} >= 0.90",
                policy="contacts.governance_rules.auto_publish",
                payload={"person": person, "email": email, "confidence": confidence})
        if confidence >= 0.70:
            return self._escalate("contact.publish",
                                  {"person": person, "email": email, "confidence": confidence},
                                  "confidence in governance-review band")
        return self._refuse("contact.publish",
                            f"confidence {confidence:.2f} below publish threshold")

    # ------------------------------------------------------------------ #
    def _refuse(self, action: str, reason: str) -> AuthorityDecision:
        return AuthorityDecision(action=action, status=ActionStatus.REFUSE, tier=3,
                                 reason=reason, policy="tier_3_refuse")


class PolicyEngineFactory:
    @staticmethod
    def load() -> PolicyEngine:
        return PolicyEngine()