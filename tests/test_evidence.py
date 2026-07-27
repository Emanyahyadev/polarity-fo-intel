"""Reproducibility primitives: content hashing, snapshots, and run manifests."""

from pathlib import Path

from fointel.evidence import (
    RunManifest,
    git_commit,
    new_manifest,
    sha256_hex,
    snapshot,
    utc_now_iso,
)


def test_sha256_is_deterministic_and_str_bytes_equivalent():
    assert sha256_hex("hello") == sha256_hex(b"hello")
    assert sha256_hex("a") != sha256_hex("b")
    assert len(sha256_hex("x")) == 64


def test_snapshot_writes_content_addressed_file_and_is_idempotent(tmp_path: Path):
    ref = snapshot('{"k": 1}', url="https://src.example/x", ext="json", snapshot_dir=tmp_path)
    assert ref.content_hash == sha256_hex('{"k": 1}')
    assert Path(ref.snapshot_path).exists()
    assert Path(ref.snapshot_path).read_text(encoding="utf-8") == '{"k": 1}'
    assert ref.url == "https://src.example/x" and ref.fetched_at is not None
    # same content -> same path, no duplication
    ref2 = snapshot('{"k": 1}', snapshot_dir=tmp_path)
    assert ref2.snapshot_path == ref.snapshot_path


def test_new_manifest_carries_provenance_of_the_run():
    m = new_manifest(stage="discovery", started_at=utc_now_iso(),
                     counts={"discovered_yielded": 192, "resolved_firms": 192})
    assert isinstance(m, RunManifest)
    assert m.stage == "discovery"
    assert m.schema_version and m.pipeline_version
    assert m.git_commit  # a sha or the honest literal "unknown"
    assert m.counts["resolved_firms"] == 192
    assert m.started_at and m.finished_at


def test_git_commit_returns_a_string():
    c = git_commit()
    assert isinstance(c, str) and c
