"""SemOpenAlex SPARQL source client.

Endpoint: https://semopenalex.org/sparql
"""

from __future__ import annotations


def search(query: str, *, mailto: str, limit: int = 500) -> list[dict]:  # pragma: no cover
    raise NotImplementedError(
        "semopenalex.search is stubbed until the SPARQL template is frozen"
    )
