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

First review cycle complete (2026-10-11 to 2026-10-17): 489 included studies, author-validated
panel (sensitivity 1.00 on the 200-record sample), conflicts adjudicated, manuscript drafted.

- Protocol frozen with SHA-256 manifests in `protocol/freeze-*.json`
  (amendments logged in `protocol/PROTOCOL.md`); registered on OSF: [doi:10.17605/OSF.IO/G7C8D](https://doi.org/10.17605/OSF.IO/G7C8D).
- Searches run in OpenAlex, NASA ADS, PubMed, IEEE Xplore, arXiv, Crossref,
  HAL and bioRxiv (via Europe PMC). Exact queries, counts and payload hashes:
  `protocol/search_strategies/`.
- Screening and extraction by a three-LLM panel on the NHR@FAU gateway; every
  vote is in `data/screening/` and `data/extraction/`. Latest counts:
  [PRISMA flow](https://akmaier.github.io/ActiveMatterLivingReview/prisma/).
- Author validation (blind title/abstract sample, full-text splits, extraction
  conflicts, seed papers) runs on the site's
  [human-check page](https://akmaier.github.io/ActiveMatterLivingReview/check/);
  exports are imported with `amlr human-import`.
- Manuscript prose is drafted by Codex and, since 2026-10-17, ChatGPT (drafting log in
  `paper/drafts/`) and reviewed by the authors; `cd paper && make paper` builds it.
- Propose a missing paper: <https://akmaier.github.io/ActiveMatterLivingReview/contribute/>
  (one YAML file in `submissions/` per pull request; checked automatically).

## Non-redistribution of subscriber content

Full-text PDFs retrieved through institutional TDM routes are cached
under `docs/`, which is **gitignored**. The public site serves only
metadata and links to each publisher's canonical URL.

## How to cite

See [`CITATION.cff`](CITATION.cff). The project text is licensed under
[CC BY 4.0](LICENSE-CC-BY-4.0); the code under the terms of
[`LICENSE`](LICENSE).
