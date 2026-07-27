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
    # below this max-similarity, the system abstains instead of answering. Tuned on the
    # bge-small model against adversarial in-vocabulary probes, because the corpus is
    # 100% family offices so off-topic queries that borrow domain words score higher than
    # naive off-topic. Measured separation: genuine queries >=0.719 (Pathstone 0.719;
    # state/type 0.75-0.80; topic 0.73-0.75); off-topic <=0.643, INCLUDING word-stuffed
    # probes ("best pizza OFFICE in chicago" 0.564, "cheap office space in Manhattan"
    # 0.567, "family offices headquartered on the moon" 0.643) and plain ones ("weather"
    # 0.41, "bake bread" 0.45, "best pizza in Chicago" 0.48). 0.68 sits in the 0.643-0.719
    # gap. Queries engineered to land in that band are the ambiguous zone (KnownLimitations).
    min_retrieval_score: float = _float("MIN_RETRIEVAL_SCORE", 0.68)

    # --- paths ---
    data_dir: str = os.getenv("DATA_DIR", "data")
    db_path: str = os.getenv("DB_PATH", "data/fointel.db")


settings = Settings()
