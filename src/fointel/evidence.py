"""
Reproducible evidence retention.

Two mechanisms make a release reproducible months later (gate-review A3):

1. Snapshots — `snapshot()` writes retrieved source content to a content-addressed
   file (sha256) and returns an `EvidenceRef` (url + fetched_at + content_hash +
   path). The hash goes into the cell's Provenance, so a re-fetched source can be
   proven identical (or shown to have drifted). Working snapshots live under
   data/raw/ (gitignored, bulky/PII); the snapshots backing the released 50 are
   bundled into docs/evidence/ at export time.

2. Run manifest — `RunManifest` records git commit, schema/pipeline version,
   timestamps, and stage counts (discovered / resolved / rejected / released /
   failures). Committed per pipeline run so any release can be tied to the exact
   code and inputs that produced it.
"""

from __future__ import annotations

import hashlib
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional, Union

from pydantic import BaseModel, Field

from . import __version__ as PIPELINE_VERSION
from .observability import get_logger
from .schema import SCHEMA_VERSION

log = get_logger("pipeline")

SNAPSHOT_DIR = Path("data/raw/snapshots")


def sha256_hex(content: Union[str, bytes]) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


class EvidenceRef(BaseModel):
    url: Optional[str] = None
    fetched_at: date
    content_hash: str
    snapshot_path: Optional[str] = None


def snapshot(content: Union[str, bytes], url: Optional[str] = None, ext: str = "json",
             snapshot_dir: Path = SNAPSHOT_DIR) -> EvidenceRef:
    """Content-address a retrieved source. Idempotent: identical content -> same file."""
    digest = sha256_hex(content)
    snapshot_dir = Path(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{digest}.{ext}"
    if not path.exists():
        path.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
    return EvidenceRef(url=url, fetched_at=_utc_today(), content_hash=digest,
                       snapshot_path=str(path))


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                             text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:  # git absent / not a repo — record honestly, never crash the run
        return "unknown"


class RunManifest(BaseModel):
    run_id: str
    stage: str
    git_commit: str
    schema_version: str
    pipeline_version: str
    started_at: str
    finished_at: str
    counts: dict = Field(default_factory=dict)
    notes: dict = Field(default_factory=dict)


def new_manifest(stage: str, counts: dict, started_at: str,
                 notes: Optional[dict] = None) -> RunManifest:
    now = datetime.now(timezone.utc)
    return RunManifest(
        run_id=now.strftime("%Y%m%dT%H%M%SZ"),
        stage=stage,
        git_commit=git_commit(),
        schema_version=SCHEMA_VERSION,
        pipeline_version=PIPELINE_VERSION,
        started_at=started_at,
        finished_at=now.isoformat(timespec="seconds"),
        counts=counts,
        notes=notes or {},
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_manifest(manifest: RunManifest, evidence_dir: str = "docs/evidence") -> Path:
    path = Path(evidence_dir) / f"run-manifest-{manifest.stage}-{manifest.run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    log.info("run manifest written", extra={"event": "manifest", "path": str(path),
                                            "stage": manifest.stage, "commit": manifest.git_commit})
    return path
