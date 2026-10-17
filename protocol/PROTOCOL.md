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
  amendment) and all records are re-screened. The author labels on the site's `/check/` page:
  the sample (fixed in `data/human_check/ta_sample.txt`) is labelled blind to the panel votes,
  and sensitivity is computed from the blind label. Labels are kept in the append-only ledger
  `data/human_check/labels.jsonl`. An author decision on a full-text split or a seed paper
  replaces the panel decision. At title/abstract, an author include sends a panel-excluded
  record to full-text retrieval; an author exclude is reported but not applied when a
  full-text assessment exists, because that assessment supersedes it.
- Reproducibility caveat: served models are not bit-for-bit deterministic even at
  temperature 0; the stored votes are the record of decision and are not re-generated. A
  model retired from the gateway is replaced only by protocol amendment, after re-calibration
  on the pilot set.

## 7. Data collection process (PRISMA 9)

Extraction form: `protocol/extraction_prompt.md` (controlled vocabularies, JSON output),
piloted on 10 included studies and then frozen with `amlr freeze` before the remaining
extractions. R1 and R3 extract independently from the full text; coded fields are compared
exactly, list fields as sets, counts within 10 %, sizes within 25 %; only disputed fields are
extracted by R2 and settled by majority (multi-label fields — phenomena, interaction modality,
theory compared — label-wise: a label is kept if at least two of the three extractors chose it);
single-valued fields with three different values are flagged for author resolution. Free-text
fields are kept from both extractors. Pilot (10 studies, 2026-10-12): 9 extracted, 2 with one
unresolved field each.
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
| 2026-10-12 | §7: multi-label extraction fields reconciled label-wise by majority instead of whole-set equality; extraction prompt frozen after the pilot | Pilot: whole-set equality left 9/9 studies with unresolved multi-label fields although most labels were shared by all extractors; label-wise majority leaves 2/9 with one genuinely disputed single-valued field |
| 2026-10-11 | §6: where no full text can be obtained after all retrieval tiers (including the author's own browser), eligibility is judged on the abstract; such records are flagged `assessment_basis: abstract_only`, reported in the PRISMA flow as "reports not retrieved — of which assessed on abstract only", and excluded in a sensitivity analysis. Conference-abstract-only records are assessed the same way (E5 applies to abstracts without results) | Author decision; avoids silently dropping eligible studies whose full text is unavailable |
| 2026-10-11 | §6: records whose only report is a conference abstract (ADS doctype `abstract`, e.g. APS March Meeting) are counted as "reports not retrieved — no full report exists"; later journal versions enter through search and citation chasing | Such records have no full text to assess; reason recorded per record |
| 2026-10-11 | §6: at title/abstract, reason-code disagreements between R1 and R2 are resolved by code precedence instead of an R3 vote | PRISMA 2020 reports title/abstract exclusions without reasons; R3 gateway latency; no inclusion decision changes (screening prompt unchanged, SHA-256 `7aeeb0b6…`) |
| 2026-10-15 | §6, §7: evidence-based conflict resolution. For every full-text split (one model dissenting) and every extraction field with three different values, each model restates its answer and quotes up to four verbatim passages (≤ 40 words each) from the full text that establish it (`protocol/evidence_prompt.md`). Each quote is checked automatically against the extracted text (verbatim / nearly verbatim / not found). The author judges on the `/check/` page from the claims and quotes; the models do not decide, and a model's revised answer on re-reading is shown but not counted as a vote. Ledger: `data/conflicts/evidence.jsonl` | Author proposal after the first validation round: judging 423 splits and 138 extraction conflicts from abstracts alone was not possible without opening every paper; the stored votes and decision rule are unchanged |
| 2026-10-17 | §6, §7: the author delegated the remaining conflicts (423 full-text splits, 167 extraction fields) to an LLM judge, Claude Opus (`judge:opus`), working from the evidence of amendment 5 and, where the quotes conflict, from the full text (`data/conflicts/judge/INSTRUCTIONS.md`; batches and decisions in `data/conflicts/judge/`). A judge decision replaces the panel decision like an author decision, is recorded with reviewer `judge:opus`, and never overrides an author label; the author may still relabel any item on `/check/`. The judge is a different model family from the panel | Author decision: manual adjudication of every conflict was not feasible; the judge's rationales are kept per item for audit |
