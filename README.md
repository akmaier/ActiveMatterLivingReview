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

## Create your own living review from a fork

Everything this review used is in the repository: the pipeline (`pipeline/`, the `amlr`
package), the site, the manuscript template, and the procedures for the browser work
([`pipeline/BROWSER.md`](pipeline/BROWSER.md)). A fork needs its own LLM endpoint, a few free
API registrations, and its own protocol. The steps below take a fork from nothing to a
published review; each command is described in more detail in
[`pipeline/README.md`](pipeline/README.md).

### 1. Fork and rename

1. Fork the repository on GitHub and clone it.
2. Turn on GitHub Pages: *Settings → Pages → Deploy from a branch → `main` / root*.
3. Edit `_config.yml` (`title`, `description`, `author`, `url`, `baseurl` — the fork's Pages
   address), `CITATION.cff`, `paper/authors.yml` and the links in this README.

### 2. Install

```bash
python3 -m venv .venv && source .venv/bin/activate      # Python 3.11 or newer
pip install -e "pipeline[dev]"
amlr --help
```

Also needed: **Google Chrome** for the browser tier of full-text retrieval, a **TeX
distribution** with `latexmk` and REVTeX 4.2 for the manuscript, and optionally Ruby with
`bundle exec jekyll serve` to preview the site locally (`Gemfile`).

### 3. Credentials

Credentials live outside the repository in `~/.config/amlr/`; templates without any token are
in `pipeline/config/`. Nothing with a token is ever committed.

```bash
mkdir -p ~/.config/amlr
cp pipeline/config/llm_api.example.toml ~/.config/amlr/llm_api.toml
cp pipeline/config/tdm_api.example.toml ~/.config/amlr/tdm_api.toml
export AMLR_MAILTO=you@your-institution.org   # contact address sent to OpenAlex, Crossref, Unpaywall
```

**LLM endpoint (required for screening and extraction).** This review used three models on
the NHR@FAU LLM gateway, which is open only to members of the German NHR centres. A fork uses
any OpenAI-compatible endpoint instead and names its three models in the `[panel]` table of
`llm_api.toml`. A free option is the hosted catalog of **NVIDIA NIM**,
<https://build.nvidia.com/explore/discover>: on any model page click *Get API Key*, sign in
with a free NVIDIA account (this joins the NVIDIA Developer Program), and copy the key. Then:

```toml
[llm]
base_url = "https://integrate.api.nvidia.com/v1"
api_key  = "nvapi-..."

[panel]
R1 = "openai/gpt-oss-20b"
R2 = "mistralai/mistral-large-2-instruct"
R3 = "deepseek-ai/deepseek-v4.1-flash"
```

These three IDs were listed by the catalog on 2026-10-28 and come from three model families,
which keeps the votes independent; they have not yet been run with this review's prompts, so
calibrate on the seed set (step 7) before screening. The catalog changes: the models of the
original panel are not served there any more. Check `GET https://integrate.api.nvidia.com/v1/models`
for current IDs. Read NVIDIA's [API trial terms](https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf)
before use: the free tier is meant for testing and evaluation, rate limits are set per model
(about 40 requests per minute is commonly reported), and NVIDIA may use the submitted content
to improve its products — so send it abstracts and open-access text, and check your
publisher licences before sending subscriber full texts (full-text screening and extraction)
to any third-party endpoint. A local server (vLLM, Ollama, LM Studio) or your institution's
own gateway avoids that question.

**Full-text and search APIs (optional; each one only adds a retrieval route).**

| Credential | Where to get it | Conditions | Goes into |
|---|---|---|---|
| Elsevier API key | <https://dev.elsevier.com/apikey/manage> (log in, request a key, accept the TDM terms) | your institution subscribes to ScienceDirect; academic research only; personal key | `[elsevier] api_key` |
| Elsevier institutional token | requested from Elsevier's Research Product APIs support, <https://service.elsevier.com/app/contact/supporthub/researchproductsapis/> | needed only outside the institution's network | `[elsevier] insttoken` |
| Wiley TDM token | <https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining> ("Get a Text and Data Mining Token", with a personal Wiley Online Library login) | institutional subscription; non-commercial research | `[wiley] tdm_token` |
| Springer Nature API key | <https://dev.springernature.com> (sign up, then *API Management*) | free basic plan | `[springer] oa_api_key`, `meta_api_key` |
| NASA ADS token | <https://ui.adsabs.harvard.edu/user/settings/token> (free ADS account) | none | `[ads] ads_token` (or `$ADS_TOKEN`) |
| IEEE Xplore API key | <https://developer.ieee.org/member/register> (IEEE reviews the request) | see IEEE's API terms | `$IEEE_API_KEY` |
| Unpaywall, OpenAlex, Crossref | no key; they ask for a contact e-mail | — | `$AMLR_MAILTO` |

`amlr config-check` shows which TDM credentials are set, without printing them. Routes whose
credential is missing are skipped; the browser tier and your own browser
([`pipeline/BROWSER.md`](pipeline/BROWSER.md)) cover what remains.

### 4. Start from a clean slate

The repository holds this review's records, decisions and manuscript. Remove them in the
fork, keeping the structure:

```bash
git rm -r -q data/screening data/extraction data/conflicts data/human_check data/snapshots \
  data/fulltext data/linkcheck data/chatgpt_context data/corpus_manifest.json data/known_records.json \
  protocol/freeze-*.json protocol/search_strategies/*-20*.txt protocol/search_strategies/pilot-*.json \
  paper/drafts paper/sections paper/tables paper/proposal paper/refs.bib paper/refs_extra.bib \
  paper/figures/prisma_figure.tex paper/figures/prisma_flow.tex \
  _data/corpus.yml _data/prisma_counts.yml assets/human_check.json assets/taxonomy.json assets/prisma_flow.svg
```

Empty `_data/changelog.yml` and restart it with your first update. `amlr prisma` and
`amlr render` regenerate the site data and the paper tables.

### 5. Write and register the protocol

| File | What to write |
|---|---|
| `protocol/PICO.md` | eligibility criteria with inclusion items and ordered exclusion codes |
| `protocol/PROTOCOL.md` | the full PRISMA-P protocol: sources, search, selection (including your panel models and endpoint), data items, risk of bias, synthesis, living procedures |
| `protocol/search_strategies/concepts.yml` | the concept blocks of the Boolean search |
| `protocol/search_strategies/seed_set.yml` | known eligible papers the search must find |
| `protocol/screening_prompt.md` | the screening instruction for the panel |
| `protocol/extraction_prompt.md` | the data items with their controlled vocabularies |
| `protocol/evidence_prompt.md` | the instruction for quoting evidence on conflicts |

If your data items differ from this review's (platform class, phenomena, …), also adapt
the code that knows them: `CODED`/`SETS` in `pipeline/src/amlr/extract.py`, `VOCAB` in
`human.py`, `SNAPSHOT_FIELDS` and the taxonomy and platform table in `render.py`, the plots in
`figures.py`, and `_pages/taxonomy.md`. Register the protocol (e.g. OSF Registries) before
screening.

### 6. Search

```bash
amlr search-count                      # hits per source for the current concept blocks
amlr search-validate                   # every seed paper must be found
amlr freeze --note "pre-search"        # SHA-256 manifest of the protocol files
amlr fetch all                         # OpenAlex, arXiv, PubMed, HAL, bioRxiv, Crossref, ADS
amlr build-corpus                      # deduplicate into data/corpus.jsonl
```

IEEE Xplore has no free Boolean search API: run the two queries printed by
`python -c "from amlr.search import render_ieee, load_concepts; print(*render_ieee(load_concepts()), sep='\n\n')"`
in Xplore's *Command Search*, export the results as CSV to
`data/raw/ieee_exports/<YYYY-MM-DD>/q1.csv` and `q2.csv`, then `amlr fetch ieee` and
`amlr build-corpus` again.

### 7. Screen titles and abstracts

```bash
amlr screen-llm --stage title_abstract --limit 50     # calibrate: all seed papers must be included
amlr freeze --note "pre-screening"
amlr screen-llm --stage title_abstract
amlr screen-report --stage title_abstract              # Fleiss' and Cohen's kappa
```

Then validate the panel yourself: `amlr render` builds the queue of the site's `/check/`
page (a blind random sample, split votes, seed papers). Push, label on the page, export, and
import the export:

```bash
amlr human-import ~/Downloads/human-check-*.json
amlr human-report                                      # panel sensitivity and specificity
```

### 8. Retrieve full texts

```bash
amlr fulltext                          # publisher TDM APIs and open access
amlr fulltext-browser                  # visible Chrome over institutional access
amlr fulltext-list                     # what is left, as a click-through list for your browser
amlr fulltext-import                   # import the PDFs you saved to ~/Downloads
amlr fulltext-abstract-only            # assess the rest on the abstract
amlr fulltext-finalize
```

How the browser tiers work and what to watch for: [`pipeline/BROWSER.md`](pipeline/BROWSER.md).
Subscriber PDFs and their text stay in gitignored folders (`docs/`, `data/fulltext_text/`).

### 9. Screen full texts, extract, resolve conflicts

```bash
amlr screen-llm --stage full_text
amlr extract --limit 10                # pilot, then freeze the extraction prompt
amlr freeze --note "extraction pilot"
amlr extract
amlr evidence                          # each model quotes its evidence on every conflict
amlr render                            # puts the conflicts on /check/
amlr human-import ~/Downloads/human-check-*.json
```

Conflicts are decided on `/check/`. A decision may also be delegated to an LLM judge: its
decisions are imported in the same export format (`amlr-human-check/1`) with its own
`reviewer` name, and an author label always overrides a judge (this review's judge criteria:
`data/human_check/opus/CRITERIA.md` in the original repository).

### 10. Publish the snapshot

```bash
amlr prisma                            # PRISMA counts and flow diagram (site and paper)
amlr render                            # corpus page, refs.bib, snapshot, taxonomy, tables
amlr figures                           # manuscript figures
git add -A && git commit -m "Snapshot <date>" && git push    # GitHub Pages rebuilds the site
```

### 11. Write the manuscript

Plan the sections in `paper/sections.yml` and the voice in `paper/STYLE_WORDS.md`. Prose can
be drafted section by section through Codex (`amlr bridge` in one terminal, `amlr draft
<section>` in another; set-up in [`pipeline/README.md`](pipeline/README.md)) or in a web chat
([`pipeline/BROWSER.md`](pipeline/BROWSER.md), section 3). Every exchange is archived in
`paper/drafts/`; disclose the AI use in the paper. Build with `cd paper && make paper`.

### 12. Keep it living

Monthly: `amlr fetch all`, `amlr build-corpus`, screen the new records (steps 7–9), then
step 10, and add an entry to `_data/changelog.yml`. A change to the protocol after freezing
is an amendment: log it in `protocol/PROTOCOL.md` and run `amlr freeze` again.

## Non-redistribution of subscriber content

Full-text PDFs retrieved through institutional TDM routes are cached
under `docs/`, which is **gitignored**. The public site serves only
metadata and links to each publisher's canonical URL.

## How to cite

See [`CITATION.cff`](CITATION.cff). The project text is licensed under
[CC BY 4.0](LICENSE-CC-BY-4.0); the code under the terms of
[`LICENSE`](LICENSE).
