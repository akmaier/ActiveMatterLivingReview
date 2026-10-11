# Active Matter Living Review

A PRISMA 2020 **living systematic review** of **robotic active matter**.

The repo is three artefacts in one:

1. A reproducible **pipeline** (`pipeline/`, the `amlr` Python package)
   that queries OpenAlex, SemOpenAlex, Crossref, arXiv, bioRxiv, PubMed,
   IEEE Xplore, HAL, NASA ADS, and Google Scholar; deduplicates;
   round-trips through ASReview for screening; and extracts a structured
   set of data items per included study.
2. A companion **website** (Jekyll, served by GitHub Pages at the repo
   root) that renders the current corpus, the PRISMA 2020 flow, and a
   change log. See `_pages/`.
3. The **manuscript source** (`paper/`, REVTeX 4.2 with the `rmp`
   option) targeted at *Reviews of Modern Physics*.

## Status

First review cycle in progress (started 2026-10-11).

- Protocol frozen with SHA-256 manifests in `protocol/freeze-*.json`
  (amendments logged in `protocol/PROTOCOL.md`); OSF registration pending.
- Searches run in NASA ADS, PubMed, IEEE Xplore, arXiv, Crossref, HAL and
  bioRxiv (via Europe PMC); OpenAlex follows once its daily credits reset.
  Exact queries, counts and payload hashes: `protocol/search_strategies/`.
- Title/abstract screening by a three-LLM panel on the NHR@FAU gateway;
  every vote is recorded in `data/screening/title_abstract-votes.jsonl`.
- Manuscript prose has not been drafted yet; it will be written by Codex
  and reviewed by the authors.

## Non-redistribution of subscriber content

Full-text PDFs retrieved through institutional TDM routes are cached
under `docs/`, which is **gitignored**. The public site serves only
metadata and links to each publisher's canonical URL.

## How to cite

See [`CITATION.cff`](CITATION.cff). The project text is licensed under
[CC BY 4.0](LICENSE-CC-BY-4.0); the code under the terms of
[`LICENSE`](LICENSE).
