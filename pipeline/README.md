# amlr — Active Matter Living Review pipeline

A thin project-specific layer over [`experteye_scraper`](../../../experteye)
that adds the sources the PRISMA 2020 review needs (bioRxiv, HAL,
SemOpenAlex, NASA ADS, Google Scholar, IEEE Xplore), a dedup/screen/
extract state machine, and the renderers that drive the Jekyll site and
the REVTeX paper.

## Bootstrap

```bash
cd /Users/maier/Documents/code/ActiveMatterLivingReview
python3 -m venv .venv && source .venv/bin/activate
pip install -e /Users/maier/Documents/code/experteye     # sibling package, editable
pip install -e pipeline[dev]
amlr --help
```

## TDM credentials

The pipeline reads TDM tokens from `tdm_api.toml`. By default it looks
at `/Users/maier/Documents/code/experteye/config/tdm_api.toml`. Override
with:

```bash
export ACTIVE_MATTER_TDM_CONFIG=/path/to/tdm_api.toml
```

The config file is never printed to logs or committed anywhere.

## CLI shape

```
amlr search          # per-source discovery → data/raw/*.jsonl
amlr dedup           # merge by DOI + normalized title → data/corpus.jsonl
amlr screen export   # emit CSV for ASReview
amlr screen import   # pull ASReview decisions back
amlr fulltext        # tier 1 (TDM) → tier 2 (Unpaywall) → tier 3 (Chrome)
amlr extract         # structured data items from screened full-text
amlr prisma          # emit PRISMA counts + flow SVG
amlr render          # emit _data/*.yml and refs.bib
amlr update          # the full pipeline, for the monthly cron
amlr draft           # call the Codex bridge for a paper section
```

Every subcommand supports `--dry-run`.
