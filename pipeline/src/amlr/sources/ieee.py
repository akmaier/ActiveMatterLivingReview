"""IEEE Xplore metadata API client.

API: https://ieeexploreapi.ieee.org/api/v1/search/articles

Reads the API key from the IEEE_API_KEY env var. If missing, the module
is a no-op; full text for IEEE DOIs is then routed through the tier-3
Chrome fetcher under the FAU VPN.
"""

from __future__ import annotations

import os


def search(query: str, *, mailto: str, limit: int = 500) -> list[dict]:  # pragma: no cover
    key = os.environ.get("IEEE_API_KEY")
    if not key:
        raise RuntimeError("IEEE_API_KEY env var not set (optional; otherwise rely on Chrome fallback)")
    raise NotImplementedError(
        "ieee.search is stubbed until the search strategy is frozen"
    )
