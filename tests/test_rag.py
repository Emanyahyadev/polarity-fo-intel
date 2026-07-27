"""RAG unit tests: filter parsing, hybrid retrieval, grounding/abstention, claim verification."""

from datetime import date

import numpy as np

from fointel.rag.ground import Grounding
from fointel.rag.index import RetrievalIndex, parse_filters
from fointel.rag.retrieve import Retrieved, retrieve
from fointel.schema import Confidence, FamilyOfficeRecord, FOType, SourceClass


def _rec(fo_id, name, fo_type=FOType.UNDETERMINED, state=None, desc=None) -> FamilyOfficeRecord:
    return FamilyOfficeRecord(fo_id=fo_id, name=name, fo_type=fo_type,
                              fo_type_evidence="ev", hq_state=state, description=desc,
                              discovery_source=SourceClass.SEC_IAPD, data_as_of=date(2026, 7, 27),
                              record_confidence=Confidence.HIGH)


def test_parse_filters_extracts_type_and_state():
    assert parse_filters("single-family offices in Texas") == {
        "fo_type": "Single-Family Office", "hq_state": "TX"}
    assert parse_filters("multi-family office") == {"fo_type": "Multi-Family Office"}
    assert parse_filters("family offices") == {}


def test_retrieve_applies_metadata_filter_and_ranks(monkeypatch):
    records = [_rec("a", "Alpha Family Office", FOType.SFO, "TX", "private equity"),
               _rec("b", "Beta Family Office", FOType.MFO, "NY", "real estate"),
               _rec("c", "Gamma Family Office", FOType.SFO, "TX", "venture capital")]
    emb = np.array([[1, 0, 0], [0, 1, 0], [0.9, 0.1, 0]], dtype=np.float32)
    index = RetrievalIndex(records, embeddings=emb)
    monkeypatch.setattr(index, "embed_query", lambda q: np.array([1, 0, 0], dtype=np.float32))

    # hard filter to SFO+TX excludes Beta (MFO, NY)
    hits = retrieve(index, "single-family offices in Texas", top_k=5,
                    filters={"fo_type": "Single-Family Office", "hq_state": "TX"})
    ids = [h.record.fo_id for h in hits]
    assert set(ids) == {"a", "c"} and "b" not in ids


def test_retrieve_empty_on_unsatisfiable_filter(monkeypatch):
    records = [_rec("a", "Alpha Family Office", FOType.SFO, "TX")]
    index = RetrievalIndex(records, embeddings=np.array([[1, 0]], dtype=np.float32))
    monkeypatch.setattr(index, "embed_query", lambda q: np.array([1, 0], dtype=np.float32))
    assert retrieve(index, "x", filters={"hq_state": "CA"}) == []


def test_grounding_abstains_below_threshold():
    g = Grounding(min_score=0.55)
    r_hi = [Retrieved(record=_rec("a", "A FO"), vector_score=0.7, bm25_score=1, rrf=0.1)]
    r_lo = [Retrieved(record=_rec("a", "A FO"), vector_score=0.4, bm25_score=1, rrf=0.1)]
    assert g.assess(r_hi)[0] is True
    assert g.assess(r_lo)[0] is False
    assert g.assess([])[0] is False


def test_verify_answer_flags_invented_firm():
    g = Grounding()
    retrieved = [Retrieved(record=_rec("a", "Pathstone Family Office"), vector_score=0.7,
                           bm25_score=1, rrf=0.1)]
    # answer names a firm not retrieved -> flagged as ungrounded
    bad = g.verify_answer("Consider Pathstone Family Office and Duquesne Capital Management.",
                          retrieved)
    assert any("Duquesne" in x for x in bad)
    # answer only names the retrieved firm -> clean
    assert g.verify_answer("Pathstone Family Office is a strong match.", retrieved) == []
