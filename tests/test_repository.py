"""Repository roundtrip + the storage-boundary guarantees (dedup, qualifying filter, audit)."""

from datetime import date

from fointel.schema import AuditEntry, Candidate, FamilyOfficeRecord, FOType, SourceClass
from fointel.store import SqliteRepository


def _repo() -> SqliteRepository:
    r = SqliteRepository(":memory:")
    r.init_schema()
    return r


def test_candidates_deduplicate_across_sources():
    r = _repo()
    c1 = Candidate(name="The Smith Family Office, LLC", source_class=SourceClass.IRS_990PF,
                   dedup_key="smith family")
    c2 = Candidate(name="Smith Family Office", source_class=SourceClass.NEWS,
                   dedup_key="smith family")
    assert r.add_candidates([c1, c2]) == 1     # same firm found by two sources -> one row
    assert r.candidate_count() == 1


def test_record_roundtrip_and_qualifying_filter():
    r = _repo()
    q = FamilyOfficeRecord(fo_id="fo_1", name="X FO", fo_type=FOType.SFO, fo_type_evidence="ev",
                           discovery_source=SourceClass.IRS_990PF, data_as_of=date(2026, 7, 27))
    nq = FamilyOfficeRecord(fo_id="fo_2", name="Y", fo_type=FOType.UNDETERMINED,
                            discovery_source=SourceClass.NEWS, data_as_of=date(2026, 7, 27))
    r.upsert_record(q)
    r.upsert_record(nq)
    assert len(r.all_records()) == 2
    assert [x.fo_id for x in r.qualifying_records()] == ["fo_1"]   # Rule 2 enforced in storage
    assert r.get_record("fo_1").name == "X FO"


def test_audit_trail_roundtrip():
    r = _repo()
    r.add_audit(AuditEntry(fo_id="fo_1", field="principal_email", rejected_value="a@b.com",
                           reason="undeliverable (SMTP 550)", source_class=SourceClass.FIRM_SITE,
                           checked_at=date(2026, 7, 27)))
    audit = r.all_audit()
    assert len(audit) == 1 and audit[0].field == "principal_email"
