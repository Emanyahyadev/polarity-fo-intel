"""
Shared HTTP client: one place for the descriptive User-Agent, retry policy, and
polite per-source rate limiting. Every discovery/enrichment source uses this, so
network behaviour (and failure handling) is consistent and observable.
"""

from __future__ import annotations

import time
from typing import Optional

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import settings
from .observability import get_logger

log = get_logger("pipeline")


class HttpClient:
    """A throttled, retrying requests session. `pause` is the minimum gap between
    calls from this client (GDELT, for example, requires >=5s)."""

    def __init__(self, user_agent: Optional[str] = None, pause: Optional[float] = None,
                 accept: str = "application/json"):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or settings.user_agent,
            "Accept": accept,
        })
        self.pause = settings.request_pause_seconds if pause is None else pause
        self._last = 0.0

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.pause:
            time.sleep(self.pause - gap)
        self._last = time.monotonic()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def _get(self, url: str, params: Optional[dict] = None) -> requests.Response:
        self._throttle()
        resp = self.session.get(url, params=params, timeout=settings.request_timeout)
        if resp.status_code == 429:
            log.warning("rate limited", extra={"event": "http_429", "url": url})
            resp.raise_for_status()  # triggers retry with backoff
        resp.raise_for_status()
        return resp

    def get(self, url: str, params: Optional[dict] = None) -> requests.Response:
        try:
            return self._get(url, params=params)
        except requests.RequestException as exc:
            # Never fail silently: log with enough context to reproduce.
            log.error("http_get_failed", extra={"event": "http_error", "url": url,
                                                 "params": params, "error": str(exc)})
            raise

    def get_json(self, url: str, params: Optional[dict] = None) -> dict:
        return self.get(url, params=params).json()

    def get_text(self, url: str, params: Optional[dict] = None) -> str:
        return self.get(url, params=params).text

    def get_with_evidence(self, url: str, params: Optional[dict] = None, ext: str = "json"):
        """Fetch AND snapshot: returns (Response, EvidenceRef) so the retrieved content
        is content-addressed for reproducible provenance. Used by enrichment/validation."""
        from .evidence import snapshot  # local import avoids an import cycle

        resp = self.get(url, params=params)
        ref = snapshot(resp.content, url=resp.url, ext=ext)
        return resp, ref
