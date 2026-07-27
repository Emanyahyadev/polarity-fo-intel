"""
End-to-end integration with MOCKED sources (no network).

Two halves of the pipeline, wired the way production wires them:
  1. discovery -> entity resolution -> persistence  (mocked DiscoverySources)
  2. release gate -> source-balanced selection       (constructed records)
"""

from datetime import date
from typing import Iterator

from fointel.discovery.base import Candidate, DiscoverySource
from fointel.discovery.harvest import harvest
from fointel.schema import (
    Confidence,
    FamilyOfficeRecord,
    FOType,
    Provenance,
    SourceClass,
    SourceRef,
)
from fointel.store import SqliteRepository
from fointel.validation.gates import ReleaseGate
from fointel.validation.selection import select_final


class MockSource(DiscoverySource):
    def __init__(self, source_class: SourceClass, candidates: list[Candidate]):
        self.source_class = source_class
        self._candidates = candidates

    def discover(self, limit: int) -> Iterator[Candidate]:
        yield from self._candidates[:limit]


def _mem_repo() -> SqliteRepository:
    r = SqliteRepository(":memory:")
    r.init_schema()
    return r


def test_discovery_resolution_persistence_no_network():
    sec = MockSource(SourceClass.SEC_EDGAR, [
        Candidate(name="Alpha Family Office", source_class=SourceClass.SEC_EDGAR,
                  raw={"cik": "1"}, hints={"state": "tx"}),
        Candidate(name="Beta Family Office", source_class=SourceClass.SEC_EDGAR,
                  raw={"cik": "2"}, hints={"state": "ny"})])
    # 'Alpha' re-surfaces from news sharing CIK 1 -> must MERGE (cross-source discovery)
    news = MockSource(SourceClass.NEWS, [
        Candidate(name="Alpha Family Office", source_class=SourceClass.NEWS,
                  raw={"cik": "1"}, hints={"state": "tx"})])

    repo = _mem_repo()
    report = harvest(repo, per_source_limit=10, sources=[sec, news])

    assert report["resolved_firms"] == 2                         # Alpha+Beta, not 3
    assert report["resolution"]["actions"].get("merge", 0) == 1  # Alpha merged across sources
    assert repo.candidate_count() == 2
    alpha = next(c for c in repo.all_candidates() if c.name == "Alpha Family Office")
    assert set(alpha.discovery_sources) == {SourceClass.SEC_EDGAR.value, SourceClass.NEWS.value}


def _releasable(fo_id, source, conf=Confidence.HIGH) -> FamilyOfficeRecord:
    def prov(sc=SourceClass.FIRM_SITE):
        return Provenance(source_class=sc, method="site fetch", checked_at=date(2026, 7, 27),
                          confidence=Confidence.HIGH)
    return FamilyOfficeRecord(
        fo_id=fo_id, name=f"{fo_id} Family Office", fo_type=FOType.SFO,
        fo_type_evidence="reputable profile + filer describe single-family office",
        fo_type_confidence=Confidence.HIGH, record_confidence=conf,
        website=f"https://{fo_id}.example", hq_country="United States",
        discovery_source=source,
        verification_sources=[SourceRef(source_class=SourceClass.FIRM_SITE, verifies="firm type",
                                        accessed_at=date(2026, 7, 27))],
        data_as_of=date(2026, 7, 27),
        provenance={"name": prov(SourceClass.SEC_EDGAR), "website": prov(),
                    "hq_country": prov(SourceClass.SEC_EDGAR)})


def test_gate_then_balanced_selection():
    records = (
        [_releasable(f"sec{i}", SourceClass.SEC_EDGAR) for i in range(8)]
        + [_releasable(f"dir{i}", SourceClass.DIRECTORY) for i in range(4)]
        + [_releasable(f"irs{i}", SourceClass.IRS_990PF) for i in range(4)]
        # one record that must NOT pass the gate (no FO evidence)
        + [FamilyOfficeRecord(fo_id="bad", name="Not An FO", fo_type=FOType.UNDETERMINED,
                              discovery_source=SourceClass.SEC_EDGAR, data_as_of=date(2026, 7, 27))]
    )
    released, outcomes = ReleaseGate().publish(records)
    assert "bad" not in {r.fo_id for r in released}               # gate blocked it
    assert len(released) == 16

    selected, report = select_final(released, target=10, max_share=0.4)  # cap 4
    assert report["selected"] == 10
    assert max(report["source_counts"].values()) <= 4            # no source dominates the shipped 10
    assert not report["cap_relaxed"]
