"""
Consistent, evidence-based SFO/MFO classification (review-board fix). Operates on the
canonical store data/final/records.json and applies ONE uniform rule, replacing every
stale/contradictory "single vs multi not established" evidence string:

  Priority:
   1. Firm's own website explicitly identifies a SINGLE family        -> Single-Family Office
   2. Firm's own website explicitly serves multiple families/clients  -> Multi-Family Office
   3. SEC Form ADV Item 5.F regulatory (client) AUM is reported       -> Multi-Family Office
   4. ACTIVE SEC adviser registration (exact CRD match)               -> Multi-Family Office
      (SEC Family Office Rule 17 CFR 275.202(a)(11)(G)-1: a bona-fide single-family office is
       EXCLUDED from adviser registration, so an actively-registered family-office adviser
       necessarily serves clients beyond one family.)
   5. otherwise (inactive/withdrawn registration, or registration status not verifiable by an
      exact identifier — name-only matches are rejected to avoid collisions)  -> Undetermined

MFO is the conservative label and may be asserted from an authoritative regulatory fact;
SFO is asserted ONLY from an explicit single-family statement. Every change is audit-logged.
Re-serializes the store + audit and re-exports. Idempotent.

    py -3.12 scripts/apply_classification.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fointel.export import export_dataset                        # noqa: E402
from fointel.rag.index import precompute_and_save                # noqa: E402
from fointel.rag.load import load_records_from_store             # noqa: E402
from fointel.schema import (AuditEntry, Confidence, FOType,      # noqa: E402
                            SourceClass, SourceRef)

AS_OF = date(2026, 7, 28)
FO_STATUS = ("An authoritative source (SEC Form 13F filing / SEC IAPD Form ADV registration, or "
             "the firm's own website) identifies it as a family office")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


_PLURAL = re.compile(r"\b(families|clients?|clientele|mandanten)\b", re.I)


def multi_quotes():
    """name -> explicit multi-family quote, from the two website re-verification rounds.
    Requires the quote to actually contain a plural families/clients indicator, so an
    ambiguous "a family office" self-description is NOT accepted as multi-family."""
    out = {}
    for f in ("data/adv/type_reverify.json", "data/adv/type_reverify_r2.json"):
        if not Path(f).exists():
            continue
        for r in json.loads(Path(f).read_text()):
            if r.get("final_type") == "Multi-Family Office" and r.get("evidence") \
                    and r.get("reason") == "explicit multi-family/client quote" \
                    and _PLURAL.search(r["evidence"]):
                out[norm(r["name"])] = r["evidence"]
    return out


def main():
    records = load_records_from_store()
    audit = [AuditEntry.model_validate(a) for a in
             json.loads(Path("data/final/audit.json").read_text())] \
        if Path("data/final/audit.json").exists() else []
    reg = json.loads(Path("data/adv/reg_status_full.json").read_text())
    qm = multi_quotes()

    changes = []
    for rec in records:
        info = reg.get(rec.name, {})
        crd, scope = info.get("crd"), info.get("scope")
        reg_aum = info.get("reg_aum")
        aum = rec.estimated_aum or ""
        ev = (rec.fo_type_evidence or "")
        old = rec.fo_type
        evl = ev.lower()
        clean = "not established" not in evl and "not establish" not in evl

        # rule 0: PRESERVE an already-clean, non-contradictory type label. The SFO gate matches
        # the SFO invariant exactly (full "single-family office" phrase, no regulatory client AUM)
        # so a preserved SFO can never fail the assert below.
        if rec.fo_type == FOType.SFO and clean and "single-family office" in evl \
                and "regulatory aum" not in aum.lower():
            new_type, new_ev, conf = FOType.SFO, ev, rec.fo_type_confidence or Confidence.MEDIUM
        elif rec.fo_type == FOType.MFO and clean and "multi-family" in evl:
            new_type, new_ev, conf = FOType.MFO, ev, rec.fo_type_confidence or Confidence.MEDIUM
        # rule 2: explicit multi-family/client website quote (plural-verified)
        elif norm(rec.name) in qm:
            new_type = FOType.MFO
            new_ev = (f"{FO_STATUS}. The firm's own website states it serves multiple families / "
                      f'clients: "{qm[norm(rec.name)][:170]}" -> multi-family office.')
            conf = Confidence.MEDIUM
        # rule 3: ADV Item 5.F regulatory (client) AUM
        elif reg_aum or "regulatory AUM" in aum:
            new_type = FOType.MFO
            new_ev = (f"{FO_STATUS}. SEC Form ADV Item 5.F reports regulatory (client) AUM "
                      f"({aum or 'reported'}); a registered adviser managing external client "
                      f"assets is a multi-family office.")
            conf = Confidence.HIGH
        # rule 4: ACTIVE registration by EXACT CRD (name-only matches rejected)
        elif crd and scope == "ACTIVE":
            new_type = FOType.MFO
            new_ev = (f"{FO_STATUS}. It is an ACTIVE SEC-registered investment adviser (IAPD CRD "
                      f"{crd}). Under the SEC Family Office Rule (17 CFR 275.202(a)(11)(G)-1) a "
                      f"bona-fide single-family office is excluded from adviser registration, so an "
                      f"actively-registered family-office adviser serves clients beyond one family "
                      f"-> multi-family office.")
            conf = Confidence.MEDIUM
        # rule 5: not establishable from an authoritative signal
        else:
            new_type = FOType.UNDETERMINED
            why = ("registration inactive/withdrawn" if scope == "INACTIVE"
                   else "adviser-registration status not verifiable by an exact identifier"
                   if not crd else "no single/multi signal")
            new_ev = (f"{FO_STATUS}; single vs multi family not established from an authoritative "
                      f"source ({why}), so honestly labelled Undetermined rather than guessed.")
            conf = Confidence.LOW

        if new_type != old or "not establish" in evl:
            if new_type != old:
                audit.append(AuditEntry(
                    fo_id=rec.fo_id, field="fo_type", rejected_value=old.value,
                    reason=f"reclassified to {new_type.value} under the uniform evidence rule "
                           f"(explicit quote / ADV Item 5.F / active registration); replaces a "
                           f"contradictory or unestablished prior label",
                    source_class=SourceClass.SEC_IAPD, checked_at=AS_OF))
                changes.append(f"{rec.name}: {old.value} -> {new_type.value}")
            rec.fo_type = new_type
            rec.fo_type_evidence = new_ev
            rec.fo_type_confidence = conf

    # ADV Item 5.F regulatory (client) AUM is DEFINITIVE evidence of multi-family status, so
    # such an MFO's type confidence is High regardless of which rule preserved/assigned it.
    for r in records:
        if r.fo_type == FOType.MFO and "regulatory AUM" in (r.estimated_aum or ""):
            r.fo_type_confidence = Confidence.HIGH
    # recompute overall confidence (weakest-link across name + type) so a lowered type
    # confidence dips the record confidence — never leave an inflated stale value.
    for r in records:
        r.record_confidence = r.compute_record_confidence()

    # invariants
    for r in records:
        assert r.qualifies(), f"{r.name}: no fo_type_evidence"
        assert "not establish" not in (r.fo_type_evidence or "").lower() \
            or r.fo_type == FOType.UNDETERMINED
        if r.fo_type == FOType.SFO:
            assert "single-family office" in (r.fo_type_evidence or "").lower()
            assert "regulatory aum" not in (r.estimated_aum or "").lower()

    Path("data/final/records.json").write_text(
        json.dumps([r.model_dump(mode="json") for r in records], indent=1, ensure_ascii=False),
        encoding="utf-8")
    Path("data/final/audit.json").write_text(
        json.dumps([a.model_dump(mode="json") for a in audit], indent=1, ensure_ascii=False),
        encoding="utf-8")
    res = export_dataset(records, audit=audit, out_dir="data/final")
    precompute_and_save(records)

    from collections import Counter
    print("===== UNIFORM CLASSIFICATION APPLIED =====")
    print(f"  changes: {len(changes)}")
    for c in changes:
        print("    ", c)
    print("  type:", dict(Counter(r.fo_type.value for r in records)))
    print(f"  audit rows: {len(audit)} | records: {res['records']}")
    # any residual contradictory evidence?
    bad = [r.name for r in records if "not establish" in (r.fo_type_evidence or "").lower()
           and r.fo_type != FOType.UNDETERMINED]
    print("  MFO/SFO rows still saying 'not established':", bad or "none")


if __name__ == "__main__":
    main()
