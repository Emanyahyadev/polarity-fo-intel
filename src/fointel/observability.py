"""
Structured observability. Every component logs through a named channel that
writes human-readable lines to the console and JSON lines to a per-channel file.

Channels (files under LOG_DIR, default ./logs):
    pipeline · validation · retrieval · api · deployment

Principle (How We Work): no silent failures. Every caught failure must log with
enough context (event, fo_id, source, error) to reproduce and diagnose it.

Usage:
    log = get_logger("pipeline")
    log.info("discovered", extra={"event": "discover", "source": "sec_adv", "count": 42})
    log.exception("source failed", extra={"event": "discover_error", "source": "news"})
"""

from __future__ import annotations

import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))

CHANNELS = {
    "pipeline": "pipeline.log",       # orchestration + shared HTTP
    "discovery": "discovery.log",     # source discovery + skipped records
    "enrichment": "enrichment.log",   # entity/principal/signal enrichment
    "validation": "validation.log",   # firm-type, email, entity-resolution/merge decisions
    "release": "release.log",         # release gates: what shipped, what was withheld and why
    "retrieval": "retrieval.log",     # RAG retrieval + grounding/abstention
    "api": "api.log",                 # serving layer
    "deployment": "deployment.log",   # deploy + health
}

# LogRecord attributes we do NOT copy into the JSON payload as "extra" fields.
_STD_ATTRS = set(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()
) | {"message", "asctime", "taskName"}


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "channel": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


_configured: set[str] = set()


def get_logger(channel: str) -> logging.Logger:
    """Return a configured logger for a channel (idempotent)."""
    if channel not in CHANNELS:
        raise ValueError(f"unknown log channel {channel!r}; known: {list(CHANNELS)}")

    logger = logging.getLogger(channel)
    if channel in _configured:
        return logger

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                                           "%H:%M:%S"))
    logger.addHandler(console)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_DIR / CHANNELS[channel], maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_JsonFormatter())
    logger.addHandler(file_handler)

    _configured.add(channel)
    return logger
