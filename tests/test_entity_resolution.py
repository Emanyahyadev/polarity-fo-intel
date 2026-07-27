"""Entity resolution: identifier merges, name+geo merges, no silent drops, logged decisions."""

from datetime import date

from fointel.entity_resolution import EntityResolver
from fointel.schema import Candidate, SourceClass


def _c(name, sc=SourceClass.SEC_EDGAR, **kw) -> Candidate:
    return Candidate(name=name, source_class=sc, discovered_at=date(2026, 7, 27), **kw)


def test_merge_on_shared_identifier_across_sources():
    a = _c("EMFO, LLC", SourceClass.SEC_EDGAR, raw={"cik": "1859434"})
    b = _c("EMFO LLC", SourceClass.NEWS, raw={"cik": "1859434"})
    resolved, decisions = EntityResolver().resolve([a, b])
    assert len(resolved) == 1                                  # one firm, two sources
    assert set(resolved[0].discovery_sources) == {
        SourceClass.SEC_EDGAR.value, SourceClass.NEWS.value}
    assert any(d.action == "merge" and d.basis.startswith("identifier") for d in decisions)


def test_merge_on_name_plus_geo():
    a = _c("Smith Family Office", hints={"state": "tx"})
    b = _c("Smith Family Office LLC", SourceClass.DIRECTORY, hints={"state": "tx"})
    resolved, _ = EntityResolver().resolve([a, b])
    assert len(resolved) == 1


def test_same_name_different_geo_stays_distinct():
    a = _c("Smith Family Office", hints={"state": "tx"})
    b = _c("Smith Family Office", hints={"state": "ny"})
    resolved, decisions = EntityResolver().resolve([a, b])
    assert len(resolved) == 2                                  # NOT silently merged
    assert any(d.action == "possible_duplicate_kept_distinct" for d in decisions)


def test_conflicting_identifiers_never_merge():
    a = _c("Acme Capital", raw={"cik": "111"}, hints={"state": "ca"})
    b = _c("Acme Capital", raw={"cik": "222"}, hints={"state": "ca"})
    resolved, _ = EntityResolver().resolve([a, b])
    assert len(resolved) == 2                                  # different CIK => different firms


def test_distinct_names_are_new_and_unique_keys():
    a = _c("Blue Capital", hints={"state": "ny"})
    b = _c("Blue Partners", hints={"state": "ny"})
    resolved, decisions = EntityResolver().resolve([a, b])
    assert len(resolved) == 2
    assert resolved[0].dedup_key != resolved[1].dedup_key
    assert [d.action for d in decisions].count("new") == 2


def test_every_candidate_produces_a_logged_decision():
    cands = [_c("A Family Office", raw={"cik": "1"}), _c("B Family Office", raw={"cik": "2"}),
             _c("A Family Office", raw={"cik": "1"})]  # third merges into first
    resolved, decisions = EntityResolver().resolve(cands)
    assert len(decisions) == len(cands)                        # nothing happens silently
    assert len(resolved) == 2
