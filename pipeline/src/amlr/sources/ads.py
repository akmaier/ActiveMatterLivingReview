"""NASA ADS source client.

API: https://api.adsabs.harvard.edu/v1/search/query

Reads the API token from the ADS_TOKEN env var.
"""

from __future__ import annotations

import os


def search(query: str, *, mailto: str, limit: int = 500) -> list[dict]:  # pragma: no cover
    token = os.environ.get("ADS_TOKEN")
    if not token:
        raise RuntimeError("ADS_TOKEN env var not set; obtain one at ui.adsabs.harvard.edu")
    raise NotImplementedError(
        "ads.search is stubbed until the search strategy is frozen"
    )
