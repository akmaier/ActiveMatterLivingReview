"""New source clients not present in experteye_scraper.

Clients:
  biorxiv, hal, semopenalex, ads, scholar, ieee.

Each module exposes `search(query: str, *, mailto: str, limit: int) -> list[dict]`
returning records shaped per `amlr.schema.Record` (plain dicts).

OpenAlex, Crossref, arXiv, PubMed/PMC, EuropePMC, Semantic Scholar are
re-exported from `experteye_scraper.sources` without modification.
"""
