"""Shared rate-limited HTTP client for source modules."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class RateLimitConfig:
    requests_per_sec: float = 3.0
    max_retries: int = 3
    backoff_base: float = 2.0
    backoff_jitter: float = 0.5
    timeout_sec: float = 30.0


class HttpClient:
    """Rate-limited HTTP client with retry and backoff."""

    def __init__(self, tool: str, email: str, config: RateLimitConfig | None = None) -> None:
        self.tool = tool
        self.email = email
        self.config = config or RateLimitConfig()
        self._last_request: float = 0.0

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request
        min_interval = 1.0 / self.config.requests_per_sec
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

    def fetch_json(self, url: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
        return self._request(url, headers)

    def fetch_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        return self._request(url, headers)

    def _request(self, url: str, headers: dict[str, str] | None = None) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self.config.max_retries + 1):
            try:
                self._rate_limit()
                req = urllib.request.Request(url)
                if headers:
                    for k, v in headers.items():
                        req.add_header(k, v)
                req.add_header("User-Agent", f"{self.tool}/1.0 (mailto:{self.email})")
                resp = urllib.request.urlopen(req, timeout=self.config.timeout_sec)
                content = resp.read()
                ct = resp.headers.get("Content-Type", "")
                if "json" in ct:
                    return json.loads(content.decode())
                return content.decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                last_exc = e
                if e.code in (429, 503):
                    retry_after = int(e.headers.get("Retry-After", str(2 ** attempt)))
                    time.sleep(retry_after)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError) as e:
                last_exc = e
                if attempt < self.config.max_retries:
                    delay = self.config.backoff_base ** attempt + self.config.backoff_jitter
                    time.sleep(delay)
                    continue
                raise
        raise RuntimeError(f"All {self.config.max_retries} retries exhausted") from last_exc

