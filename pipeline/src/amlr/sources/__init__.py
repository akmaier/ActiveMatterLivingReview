"""Source clients for the databases without a request builder in `amlr.search`.

Clients:
  biorxiv, hal, semopenalex, ads, scholar, ieee.

Each module exposes `search(query: str, *, mailto: str, limit: int) -> list[dict]`
returning records shaped per `amlr.schema.Record` (plain dicts).

OpenAlex, Crossref, arXiv, PubMed and Europe PMC are queried directly by `amlr.search`.
"""
