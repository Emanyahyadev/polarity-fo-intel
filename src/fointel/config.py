"""
Environment-aware configuration. Config-driven, no secrets in code.

Values are read from environment variables (optionally via a local .env file,
which is gitignored). See .env.example for the full list and defaults.

Lives inside the package so it imports cleanly everywhere (tests, scripts, the
deployed server) without path juggling. Static config *assets* (sector taxonomy,
seed queries) live under the top-level config/ directory instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


@dataclass(frozen=True)
class Settings:
    # --- targets ---
    target_records: int = _int("TARGET_RECORDS", 50)
    # discover a larger pool than we ship; only qualifying records count toward 50
    pool_multiplier: float = _float("POOL_MULT", 4.0)

    # --- HTTP / discovery ---
    # SEC EDGAR & IRS ask for a descriptive UA with contact info; set yours in .env
    user_agent: str = os.getenv(
        "USER_AGENT",
        "PolarityFOIntel/0.1 (family-office intelligence assessment; set contact in .env)",
    )
    request_timeout: int = _int("REQUEST_TIMEOUT", 30)
    request_pause_seconds: float = _float("REQUEST_PAUSE", 0.5)  # polite rate limiting

    # --- email verification (validation layer) ---
    smtp_from: str = os.getenv("SMTP_FROM", "verify@example.com")
    smtp_timeout: int = _int("SMTP_TIMEOUT", 10)

    # --- RAG (wired at Wave 3) ---
    llm_provider: str = os.getenv("LLM_PROVIDER", "groq")   # free-tier default
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    embed_model: str = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

    # --- retrieval / grounding control ---
    retrieval_top_k: int = _int("RETRIEVAL_TOP_K", 5)
    # below this max-similarity, the system abstains instead of answering
    min_retrieval_score: float = _float("MIN_RETRIEVAL_SCORE", 0.35)

    # --- paths ---
    data_dir: str = os.getenv("DATA_DIR", "data")
    db_path: str = os.getenv("DB_PATH", "data/fointel.db")


settings = Settings()
