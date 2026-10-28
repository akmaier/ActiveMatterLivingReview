"""OpenAI-compatible chat client for the NHR@FAU (RRZE) LLM gateway, or any other
OpenAI-compatible endpoint. Credentials are passed in by `amlr.llm`."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


DEFAULT_BASE_URL = "https://hub.nhr.fau.de/api/llmgw/v1"


class RRZEClientError(RuntimeError):
    pass


class RRZERateLimit(RRZEClientError):
    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class RRZETimeout(RRZEClientError):
    pass


@dataclass(frozen=True)
class LLMResponse:
    content: str
    finish_reason: str
    model: str
    raw: dict[str, Any]


Transport = Callable[[str, dict[str, str], bytes, float], dict[str, Any]]


def _parse_retry_after(value: str | None) -> int | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    return None


class RRZEClient:
    """Small OpenAI-compatible chat client for the RRZE/NHR gateway.

    The class reads no credentials itself; `amlr.llm.client_for` passes them in.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
        transport: Transport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.transport:
            data = self.transport(f"{self.base_url}/chat/completions", headers, body, self.timeout_seconds)
        else:
            data = self._post_json(f"{self.base_url}/chat/completions", headers, body)
        return self._parse_response(data)

    def _post_json(self, url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            retry_after = _parse_retry_after(exc.headers.get("Retry-After"))
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code in (429, 503):
                raise RRZERateLimit(
                    f"RRZE backend rate-limited request with HTTP {exc.code}: {detail[:500]}",
                    retry_after_seconds=retry_after,
                ) from exc
            raise RRZEClientError(f"RRZE request failed with HTTP {exc.code}: {detail[:500]}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise RRZETimeout(f"RRZE request timed out after {self.timeout_seconds:g}s") from exc
        except urllib.error.URLError as exc:
            raise RRZEClientError(f"RRZE request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RRZEClientError(f"RRZE returned invalid JSON: {exc}") from exc

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        choices = data.get("choices") or []
        if not choices:
            raise RRZEClientError("RRZE response had no choices")
        first = choices[0]
        message = first.get("message") or {}
        content = str(message.get("content") or "")
        finish_reason = str(first.get("finish_reason") or "")
        model = str(data.get("model") or self.model)
        return LLMResponse(content=content, finish_reason=finish_reason, model=model, raw=data)
