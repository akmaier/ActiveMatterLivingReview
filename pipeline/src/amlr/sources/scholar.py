"""Google Scholar source client via `scholarly`.

Scholar is treated as a *supplementary* source: it has no reproducible
query API, so it is documented in the protocol as a seed/verification
channel, not a PRISMA primary source.
"""

from __future__ import annotations


def search(query: str, *, mailto: str, limit: int = 100) -> list[dict]:  # pragma: no cover
    raise NotImplementedError(
        "scholar.search is stubbed until the scholarly wrapper is wired in"
    )
