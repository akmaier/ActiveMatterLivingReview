"""HAL (Hyper Articles en Ligne) source client.

API: https://api.archives-ouvertes.fr/search/
"""

from __future__ import annotations


def search(query: str, *, mailto: str, limit: int = 500) -> list[dict]:  # pragma: no cover
    raise NotImplementedError(
        "hal.search is stubbed until the search strategy is frozen"
    )
