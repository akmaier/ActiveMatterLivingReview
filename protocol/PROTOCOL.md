# Protocol: A living systematic review of robotic active matter

Status: **DRAFT — not frozen, not registered.** Freeze = tag `protocol-v1` + OSF Registries
submission, both before the first screening decision. Amendments after freezing are new,
dated entries in the amendment log; earlier text is never edited in place.

Reporting standard: PRISMA 2020 (Page et al., BMJ 2021;372:n71), checklist mapping in
`prisma_checklist.md`. Living-review conventions follow Elliott et al. (2017).

Prose marked `[CODEX-DRAFT]` is authored by Codex via the bridge; everything else is a
structured decision recorded by the review team.

## 1. Rationale (PRISMA 3) — [CODEX-DRAFT]

## 2. Objectives (PRISMA 4)

- O1. Map which robotic platforms have been used as experimental realizations of active matter.
- O2. Identify which collective phenomena (e.g. flocking, clustering, motility-induced phase
  separation, chirality, active solids/odd elasticity) have been observed in robotic systems.
- O3. Establish which theoretical frameworks have been quantitatively tested against robotic
  experiments, and with what agreement.
- O4. Characterize how control and programmability (feedback, sensing, learning) are used to
  tune collective behavior.
- O5. Assess reproducibility (replication, data/code availability) of the evidence base.

## 3. Eligibility criteria (PRISMA 5)

Operationalized in `PICO.md`. Open scope questions are listed there and must be resolved
before freezing.

## 4. Information sources (PRISMA 6)

| Source | Interface | Role |
|---|---|---|
| OpenAlex | REST `api.openalex.org/works`, `title_and_abstract.search` | primary (credit-metered: ~100 searches/day) |
| SemOpenAlex | SPARQL `semopenalex.org/sparql` | fallback for metadata and citation lookups when OpenAlex credits are exhausted; no abstracts or text search, lags OpenAlex, so not a separate search source |
| Crossref | REST `api.crossref.org/works`, `query.bibliographic` | primary; no Boolean search, so one relevance query (top 100) per AND-pair and phrase, then the same Boolean logic applied locally to title + abstract; non-report types (e.g. `component` = supplementary files, `dataset`, `peer-review`) are removed before screening and counted in the strategy file |
| arXiv | `export.arxiv.org/api/query` | primary (all categories; title and abstract) |
| bioRxiv | Europe PMC preprint index, `PUBLISHER:"bioRxiv"` | primary (bioRxiv's own API has no keyword search) |
| PubMed | NCBI E-utilities | primary |
| IEEE Xplore | Command Search (web, FAU institutional access), Abstract field | primary; two queries within IEEE's 25-terms-per-clause and 10-wildcard limits (`amlr.search.render_ieee`), results exported as CSV |
| HAL | `api.archives-ouvertes.fr/search` | primary |
| NASA ADS | `api.adsabs.harvard.edu/v1` | primary |
| Google Scholar | `scholarly` | **supplementary** (not reproducible; reported separately) |
| Citation chasing | OpenAlex references/cited-by of included studies | supplementary |
| Hand-search | ToCs of RMP, PRX, PRL, PRE, Soft Matter, Science Robotics, Nature Physics, 2004–present | supplementary |

Date coverage: database inception to the run date. Language: English.

## 5. Search strategy (PRISMA 7)

Concept blocks live in `search_strategies/concepts.yml`; the logic is
`(ACTIVE-MATTER AND ROBOTIC-AGENT) OR (COLLOID AND CONTROL) OR COMPOSITE-PHRASES`, where
the colloid-and-control branch captures Janus and other synthetic active particles under
programmable or feedback control (`PICO.md`, E6). `amlr search` renders the
per-source syntax and writes one dated file per source and run
(`search_strategies/<source>-<YYYY-MM-DD>.txt`) with the exact query string, run timestamp,
record count, and SHA-256 of the raw payload. Sources without server-side Boolean search
(Crossref, bioRxiv) are queried per phrase and filtered locally with the same blocks; the
filter code version is recorded.

Sensitivity check: known-item recall on `search_strategies/seed_set.yml` (`amlr
search-validate`); every seed paper must be retrieved by at least one primary source before
freezing. Pilot of 2026-10-11 (`pilot-2026-10-11.json`): 12/12 seed papers retrieved; hit
counts OpenAlex 7,115, PubMed 983, arXiv 695, HAL 147, bioRxiv 44 (before deduplication).

Peer review of the search: PRESS 2015 checklist by a second person before freezing.

## 6. Selection process (PRISMA 8)

- Deduplication: DOI canonicalization, then normalized-title Jaccard ≥ 0.9 (`amlr.dedup`);
  merged records keep all source IDs.
- Reviewers: a panel of three large language models served on the NHR@FAU LLM gateway
  (`https://hub.nhr.fau.de/api/llmgw/v1`, OpenAI-compatible):

  | Reviewer | Gateway model ID |
  |---|---|
  | R1 | `gpt-oss-120b` |
  | R2 | `GaleneAI/Magistral-Small-2509-FP8-Dynamic` |
  | R3 | `deepseek-ai/DeepSeek-V4-Flash-0731` |

- Independence: each model screens every record in a fresh context, without access to the
  other models' votes. Instructions are the frozen screening prompt
  (`protocol/screening_prompt.md`, SHA-256 pinned at freezing), temperature 0.
- Output per vote: include/exclude, one exclusion code (E1–E6, `PICO.md`), confidence, and a
  ≤ 40-word rationale. Every vote is stored with reviewer, gateway-reported model string,
  prompt SHA-256, timestamp, and the raw response (`data/screening/*-votes.jsonl`).
- Decision rule (both stages): a record is included when ≥ 2 of 3 reviewers vote include.
  The exclusion reason is the majority code, or the highest-precedence code if all three
  differ. Title/abstract: records without an abstract proceed to full text unless all three
  reviewers exclude on the title.
- Vote sequencing: R1 and R2 vote on every record; R3 votes only where its vote can change
  the outcome — R1 and R2 disagree, both exclude a record without an abstract, or (full text
  only) both exclude with different codes — so every inclusion decision equals that of a full
  three-vote majority. At title/abstract, PRISMA 2020 reports exclusions as a count without
  reasons, so differing codes are resolved by precedence rather than by R3
  (the conventional two-reviewers-plus-arbiter design). R3 additionally votes on a fixed
  10 % audit sample (deterministic by record-ID hash), on which Fleiss' κ is reported.
  Reason: R3's gateway latency (~10 min per vote on 2026-10-11) made full triple screening
  infeasible; the decision rule itself is unchanged.
- Full text: the same panel and rule, on text extracted from the retrieved report.
- Agreement: Fleiss' κ across the panel and pairwise Cohen's κ, reported per stage.
- Calibration (before screening): every eligible paper in `search_strategies/seed_set.yml`
  must be included by the panel at the title/abstract stage; otherwise the prompt is revised
  and the check repeated before it is frozen.
- Validation (after panel screening, by the author): the author independently labels a
  random sample of 200 title/abstract records and all 1-of-3 split votes at full text, to
  report panel sensitivity and specificity and to retain human accountability for the final
  inclusion set. If title/abstract sensitivity is < 0.95, the prompt is amended (logged as an
  amendment) and all records are re-screened.
- Reproducibility caveat: served models are not bit-for-bit deterministic even at
  temperature 0; the stored votes are the record of decision and are not re-generated. A
  model retired from the gateway is replaced only by protocol amendment, after re-calibration
  on the pilot set.

## 7. Data collection process (PRISMA 9)

Extraction form: `protocol/extraction_prompt.md` (controlled vocabularies, JSON output),
piloted on 10 included studies and then frozen with `amlr freeze` before the remaining
extractions. R1 and R3 extract independently from the full text; coded fields are compared
exactly, list fields as sets, counts within 10 %, sizes within 25 %; only disputed fields are
extracted by R2 and settled by majority; fields with three different values are flagged for
author resolution. Free-text fields are kept from both extractors.
Missing items are recorded as missing, not imputed. Authors are not contacted for the
initial version.

## 8. Data items (PRISMA 10)

Platform class and model; number of agents; agent size and speed; propulsion mechanism;
interaction modality (contact, hydrodynamic, sensing/communication); control architecture
(none / on-board rules / external feedback / learned); environment and boundary
conditions; observed collective phenomena; observables and order parameters reported;
theoretical model compared and the agreement metric; number of independent runs; data and
code availability.

## 9. Risk of bias / study quality (PRISMA 11)

No validated tool exists for robotic active-matter experiments. We use a pre-specified
six-domain rating (low / some concerns / high): D1 replication (independent runs reported);
D2 characterization of agent heterogeneity; D3 finite-size and boundary effects addressed;
D4 validity of the tracking/measurement method; D5 data and code availability; D6
quantitative (not only qualitative) comparison to theory. All three reviewers rate
independently; the per-domain rating is the majority, or "some concerns" if all three differ.

## 10. Effect measures (PRISMA 12)

Not applicable in the meta-analytic sense; outcomes are heterogeneous observables. We report
the observables as given and, where a theory comparison is made, the agreement metric used.

## 11. Synthesis methods (PRISMA 13)

Narrative synthesis organized by a taxonomy derived from the data items; evidence maps
(platform × phenomenon, phenomenon × theoretical framework); bibliometric trends. No
meta-analysis or vote counting. Sensitivity: syntheses repeated excluding studies rated
high risk in D1 or D6.

## 12. Reporting bias and certainty (PRISMA 14–15)

Publication-bias assessment via comparison of preprint-only vs. peer-reviewed findings.
Certainty per synthesis statement: high / moderate / low, based on number of independent
platforms and groups reproducing the finding and the D1/D6 ratings.

## 13. Living-review procedures

- Searches re-run monthly; screening of new records is batched per update.
- Each update produces a dated snapshot (`data/snapshots/<date>/`), an updated-review PRISMA
  flow, and a change-log entry on the website.
- The manuscript is re-versioned when the synthesis changes materially (criteria to be
  specified: new platform class, new phenomenon, or reversal of a certainty rating).

## 14. Registration, support, competing interests, data availability (PRISMA 24–27)

- Registration: OSF Registries — `[to be filled after registration]`.
- Support / funding: `[to be filled]`.
- Competing interests: `[to be filled]`.
- Availability: code (`pipeline/`), search strings, decisions, extraction data, and
  snapshots are public in this repository; subscriber full texts are not redistributed.
- Use of AI tools: manuscript prose is drafted by an AI system (Codex) and reviewed by the
  authors; all exchanges are archived in `paper/drafts/` and disclosed in the paper, as
  required by APS policy.

## Amendment log

| Date | Change | Reason |
|---|---|---|
| 2026-10-11 | §7: extraction form specified (`protocol/extraction_prompt.md`) with field-comparison rules | Instrument completed before any extraction; no data affected |
| 2026-10-11 | §6: at title/abstract, reason-code disagreements between R1 and R2 are resolved by code precedence instead of an R3 vote | PRISMA 2020 reports title/abstract exclusions without reasons; R3 gateway latency; no inclusion decision changes (screening prompt unchanged, SHA-256 `7aeeb0b6…`) |
