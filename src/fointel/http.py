"""
Shared HTTP client: one place for the descriptive User-Agent, retry policy, and
polite per-source rate limiting. Every discovery/enrichment source uses this, so
network behaviour (and failure handling) is consistent and observable.
"""

from __future__ import annotations

import time
from typing import Optional

import requests

from .config import settings
from .observability import get_logger

log = get_logger("pipeline")


class HttpClient:
    """A throttled, retrying requests session.

    `pause`   — minimum gap between calls from this client (GDELT needs >=5s).
    `timeout` — per-request timeout (short for flaky firm websites).
    `max_attempts` — total tries incl. the first (1 = no retry, for slow web pages).
    """

    def __init__(self, user_agent: Optional[str] = None, pause: Optional[float] = None,
                 accept: str = "application/json", timeout: Optional[int] = None,
                 max_attempts: int = 3):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or settings.user_agent,
            "Accept": accept,
        })
        self.pause = settings.request_pause_seconds if pause is None else pause
        self.timeout = settings.request_timeout if timeout is None else timeout
        self.max_attempts = max(1, max_attempts)
        self._last = 0.0

    def _throttle(self) -> None:
        gap = time.monotonic() - self._last
        if gap < self.pause:
            time.sleep(self.pause - gap)
        self._last = time.monotonic()

    def get(self, url: str, params: Optional[dict] = None) -> requests.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(self.max_attempts):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
                if resp.status_code == 429:
                    log.debug("rate limited", extra={"event": "http_429", "url": url})
                    resp.raise_for_status()
                resp.raise_for_status()
                return resp
            except requests.RequestException as exc:
                last_exc = exc
                if attempt + 1 < self.max_attempts:
                    time.sleep(min(2 ** attempt, 20))  # backoff between retries only
        log.warning("http_get_failed", extra={"event": "http_error", "url": url,
                                             "params": params, "error": str(last_exc)})
        raise last_exc  # type: ignore[misc]

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
