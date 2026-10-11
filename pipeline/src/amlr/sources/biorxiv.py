"""bioRxiv / medRxiv source client.

API: https://api.biorxiv.org/details/{server}/{DOI|interval}

The free API returns records in windows; a keyword search is done
client-side (bioRxiv itself has no server-side keyword search). To
stay reproducible under PRISMA, we fetch a dated window of records
and filter locally against the frozen query terms.
"""

from __future__ import annotations

from typing import Iterable


def search(query: str, *, mailto: str, limit: int = 500) -> list[dict]:  # pragma: no cover
    raise NotImplementedError(
        "biorxiv.search is stubbed until the search strategy is frozen"
    )
