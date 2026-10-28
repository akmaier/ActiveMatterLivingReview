# amlr — Active Matter Living Review pipeline

The pipeline behind the review: the sources the PRISMA 2020 search needs (OpenAlex,
SemOpenAlex, Crossref, arXiv, bioRxiv, PubMed, IEEE Xplore, HAL, NASA ADS, Google Scholar),
a dedup/screen/extract state machine, and the renderers that drive the Jekyll site and
the REVTeX paper. It is self-contained: everything it needs installs from PyPI.

## Bootstrap

From the repository root:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e "pipeline[dev]"
amlr --help
```

## Credentials

Nothing is needed for the open sources. Two optional files unlock the rest; both live
outside the repository and are never printed or committed.

| File (default location) | Override | Template | Used by |
|---|---|---|---|
| `~/.config/amlr/tdm_api.toml` | `$ACTIVE_MATTER_TDM_CONFIG` | `pipeline/config/tdm_api.example.toml` | `amlr fulltext` (publisher TDM routes), NASA ADS search |
| `~/.config/amlr/llm_api.toml` | `$AMLR_LLM_CONFIG`, or `RRZE_LLM_API_KEY` in the environment | `pipeline/config/llm_api.example.toml` | the LLM screening and extraction panel |

```bash
mkdir -p ~/.config/amlr
cp pipeline/config/tdm_api.example.toml ~/.config/amlr/tdm_api.toml   # then fill in
cp pipeline/config/llm_api.example.toml ~/.config/amlr/llm_api.toml   # then fill in
```

`amlr fulltext` needs `tdm_api.toml` to exist; every key in it is optional, and a route
without its credential is skipped. The IEEE Xplore key comes from `$IEEE_API_KEY`, the ADS
token alternatively from `$ADS_TOKEN` or `~/.config/amlr/ads_token`, and the contact address
for OpenAlex, Crossref and Unpaywall from `$AMLR_MAILTO`. Where to obtain each key, and how
to point the LLM panel at another OpenAI-compatible endpoint (e.g. NVIDIA NIM): the
repository README, "Create your own living review from a fork", step 3.

The LLM panel reads its endpoint from `[llm]` (or `AMLR_LLM_API_KEY` and
`AMLR_LLM_BASE_URL`) and its three models from `[panel]` (or `AMLR_PANEL_R1..R3`); without
either, it uses the models of the published review on the NHR@FAU gateway.

## Commands

```
amlr config-check            which TDM credentials are set (never their values)
amlr search-count            hits per source for the current concept blocks
amlr search-validate         known-item recall on the seed set
amlr freeze --note TEXT      SHA-256 manifest of the frozen protocol files
amlr fetch SOURCE|all        retrieve records into data/raw/ and log the dated strategy file
amlr build-corpus            deduplicate the latest retrievals into data/corpus.jsonl
amlr screen-llm              three-LLM panel, --stage title_abstract | full_text
amlr screen-report           Fleiss' and pairwise Cohen's kappa per stage
amlr fulltext                full texts, tier 1 (publisher TDM) and tier 2 (open access)
amlr fulltext-browser        tier 3, visible Chrome over institutional access (BROWSER.md)
amlr fulltext-list           click-through list of what is still missing, for your browser
amlr fulltext-import         import the PDFs you saved
amlr fulltext-abstract-only  assess the rest on the abstract
amlr fulltext-finalize       mark what is still missing as not retrieved
amlr extract                 panel data extraction and risk-of-bias rating
amlr evidence                verbatim evidence from each model on every conflict
amlr human-queue             the queue behind the site's /check/ page
amlr human-import FILE...    import labels exported from /check/
amlr human-report            panel sensitivity, specificity and kappa against your labels
amlr prisma                  PRISMA counts and flow diagram (site and paper)
amlr render                  site data, refs.bib, snapshot, taxonomy, /check/ queue, tables
amlr figures                 manuscript figures from the latest snapshot
amlr bridge                  local Codex bridge for `amlr draft`
amlr draft SECTION           have Codex draft one section from paper/sections.yml
amlr screen-export           CSV for ASReview Lab (optional)
amlr dedup FILES...          merge arbitrary JSONL files (low-level)
```

`amlr COMMAND --help` lists each command's options. The order in which they are run for a
review is in the repository README, steps 6 to 12.

## Drafting with Codex

`amlr draft SECTION` assembles the prompt for one section of `paper/sections.yml` (the
evidence table of the latest snapshot, the PRISMA counts, the protocol, the voice guide),
sends it to Codex, and stores the reply verbatim in `paper/sections/`, with the whole
exchange archived in `paper/drafts/`. `--dry-run` prints the prompt instead.

Codex is reached through a small local bridge in this package, `amlr bridge`:

1. Install Codex (the `codex` command line, or the ChatGPT desktop app, which bundles it) and
   sign in.
2. Start a Codex task for the manuscript and note its id: the task's session file is
   `~/.codex/sessions/.../*-<id>.jsonl`.
3. Write the id to `~/.config/amlr/codex_thread` (or pass `--thread-id`, or set
   `CODEX_THREAD_ID`).
4. Run `amlr bridge` in one terminal and `amlr draft SECTION` in another.

The bridge listens on `127.0.0.1:8766` only, runs every turn in Codex's read-only sandbox,
handles one request at a time, and gives up a turn after 3000 s (`--timeout`). With
`CODEX_BRIDGE_TOKEN` set it requires that bearer token; `amlr draft` sends the same variable.
`CODEX_BRIDGE_URL` points `amlr draft` at a bridge elsewhere. `amlr bridge --help-bridge`
lists all options.

Without Codex, the sections can be drafted in a web chat instead: BROWSER.md, section 3.
