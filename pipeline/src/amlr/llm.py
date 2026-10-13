"""NHR@FAU LLM gateway access for the reviewer panel.

Reuses experteye's OpenAI-compatible `RRZEClient`. The API key comes from the environment
(RRZE_LLM_API_KEY / EXPERTEYE_LLM_API_KEY / NHR_LLM_API_KEY) or, failing that, from the
`[llm]` table only of `$AMLR_LLM_CONFIG` (default: experteye's config/llm_api.toml).
"""

from __future__ import annotations

import http.client
import json
import os
import re
import time
import tomllib
from pathlib import Path

from experteye_scraper.scrum.rrze_client import (
    DEFAULT_BASE_URL,
    LLMResponse,
    RRZEClient,
    RRZEClientError,
    RRZERateLimit,
    RRZETimeout,
    Transport,
)

PANEL: dict[str, str] = {
    "R1": "gpt-oss-120b",
    "R2": "GaleneAI/Magistral-Small-2509-FP8-Dynamic",
    "R3": "deepseek-ai/DeepSeek-V4-Flash-0731",
}

DEFAULT_LLM_CONFIG = Path("/Users/maier/Documents/code/experteye/config/llm_api.toml")
_ENV_KEYS = ("RRZE_LLM_API_KEY", "EXPERTEYE_LLM_API_KEY", "NHR_LLM_API_KEY")


def _credentials() -> tuple[str, str]:
    for name in _ENV_KEYS:
        if os.environ.get(name, "").strip():
            base = os.environ.get("RRZE_LLM_BASE_URL", "").strip() or DEFAULT_BASE_URL
            return base, os.environ[name].strip()
    path = Path(os.environ.get("AMLR_LLM_CONFIG", DEFAULT_LLM_CONFIG))
    if not path.exists():
        raise RRZEClientError(f"no LLM API key in env ({', '.join(_ENV_KEYS)}) and no {path}")
    with path.open("rb") as fh:
        llm = tomllib.load(fh).get("llm", {})
    if not llm.get("api_key"):
        raise RRZEClientError(f"{path} has no [llm].api_key")
    return llm.get("base_url", DEFAULT_BASE_URL), llm["api_key"]


def client_for(model: str, *, timeout_s: float = 300, transport: Transport | None = None) -> RRZEClient:
    if transport is not None:
        return RRZEClient(base_url=DEFAULT_BASE_URL, api_key="test", model=model,
                          timeout_seconds=timeout_s, transport=transport)
    base, key = _credentials()
    return RRZEClient(base_url=base, api_key=key, model=model, timeout_seconds=timeout_s)


def chat(client: RRZEClient, system: str, user: str, *, max_tokens: int = 4096,
         retries: int = 4) -> LLMResponse:
    """Chat at temperature 0, retrying rate limits (honoring Retry-After) and timeouts."""

    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in range(retries + 1):
        try:
            return client.chat(messages, temperature=0.0, max_tokens=max_tokens)
        except RRZERateLimit as e:
            if attempt == retries:
                raise
            time.sleep(e.retry_after_seconds or 10 * 2**attempt)
        except RRZETimeout:
            if attempt == retries:
                raise
            time.sleep(5 * 2**attempt)
        except RRZEClientError as e:
            # The gateway (LiteLLM) surfaces transient backend failures as HTTP 5xx.
            if attempt == retries or not _SERVER_ERROR.search(str(e)):
                raise
            time.sleep(5 * 2**attempt)
        except (OSError, http.client.HTTPException) as e:
            # Dropped connections (RemoteDisconnected, resets) are not wrapped by RRZEClient.
            if attempt == retries:
                raise RRZEClientError(f"network error after {retries + 1} attempts: {type(e).__name__}: {e}") from e
            time.sleep(5 * 2**attempt)
    raise AssertionError("unreachable")


_SERVER_ERROR = re.compile(r"HTTP 5\d\d")


_THINK = re.compile(r"<think>.*?</think>|\[THINK\].*?\[/THINK\]", re.DOTALL | re.IGNORECASE)


def parse_json_object(text: str, required_key: str) -> dict:
    """Return the last JSON object in `text` that has `required_key`.

    Tolerates reasoning traces (<think>, [THINK]) and ```json fences around the answer.
    """

    text = _THINK.sub("", text)
    # strict=False: models sometimes copy raw control characters (e.g. from PDF text) into strings.
    decoder = json.JSONDecoder(strict=False)
    found: dict | None = None
    for i, ch in enumerate(text):
        if ch != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(text, i)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and required_key in obj:
            found = obj
    if found is None:
        raise ValueError(f"no JSON object with '{required_key}' in model output: {text[:200]!r}")
    return found
