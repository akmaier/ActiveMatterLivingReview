# OSF registration — prefill text (Generalized Systematic Review Registration)

Retrospective note for every field: the protocol was frozen on 2026-10-11 (SHA-256 manifests in
`protocol/freeze-*.json`) before screening began; seven dated amendments since are listed in the
amendment log of `protocol/PROTOCOL.md`. This registration documents the frozen protocol and the
amendments; the first review cycle (2026-10-11 to 2026-10-17) was completed before registration.

**Title:** Robotic active matter: a living systematic review (PRISMA 2020)

**Description:** Living systematic review of physical collectives of at least two interacting,
self-propelled or actively driven artificial agents (robots, robotic micro/nano-agents, programmable
active particles, robotic active solids) that report a quantitative collective or interaction
observable. Screening and extraction by a panel of three LLMs with author validation; evidence-based
adjudication of conflicts. Protocol, search strings, all votes, extraction data and snapshots:
https://github.com/akmaier/ActiveMatterLivingReview — website: https://akmaier.github.io/ActiveMatterLivingReview/

**Contributors:** Andreas Maier (FAU), Siming Bayer (FAU), M. Delens (ULiège), Isa Mammadli (FAU),
M. Mélard (ULiège), Siddhant Mohapatra (FAU), Maxime Noirhomme (ULiège), Filip Novkoski (FAU/ULiège),
Jayant Pande (FLAME University), Prajol Shrestha (FAU), Ana-Sunčana Smith (FAU/RBI), N. Vanesse
(ULiège), F. Wéry (ULiège), Nicolas Vandewalle (ULiège). Only those with OSF accounts can be added.

**Subjects:** Physical Sciences and Mathematics > Physics (Statistical, Nonlinear, and Soft Matter
Physics); Engineering > Robotics. **Tags:** active matter, swarm robotics, collective behavior,
living systematic review, PRISMA. **License:** CC-BY 4.0.

## Study information
- **Type of review:** Systematic review (living), narrative synthesis with evidence maps.
- **Review stages completed:** preparation, search, screening, extraction, synthesis (first cycle).
- **Current stage:** first cycle complete; monthly updates.
- **Start date:** 2026-10-11. **End date:** open (living review; first cycle ended 2026-10-17).
- **Background:** Robots allow active-matter physics to be tested with controlled, programmable
  agents, but the evidence is spread across physics and robotics and has not been synthesized
  against theory.
- **Primary research questions:** O1 platforms used as experimental realizations of active matter;
  O2 collective phenomena observed; O3 theoretical frameworks tested quantitatively and with what
  agreement.
- **Secondary research questions:** O4 how control and programmability tune collective behavior;
  O5 reproducibility (replication, data/code availability).
- **Expectations / hypotheses:** none (descriptive and evaluative synthesis).
- **Dependent variables:** collective phenomena and observables; theory–experiment agreement.
- **Independent variables:** platform class, agent number and size, propulsion, interaction
  modality, control architecture, environment.
- **Additional variables:** independent runs, data and code availability, six risk-of-bias domains.
- **Software:** `amlr` pipeline (Python), repository above.
- **Funding:** none. **Conflicts of interest:** none. **Overlapping authorships:** several authors
  co-authored included studies (the PULS/GRASP brainbot papers); their inclusion was decided by the
  author-recorded seed decisions, which are logged.

## Search strategy
- **Databases:** OpenAlex, Crossref, arXiv, bioRxiv (via Europe PMC), PubMed, IEEE Xplore, HAL,
  NASA ADS; supplementary: Google Scholar, citation chasing, hand-search; reader submissions via
  GitHub pull requests (records identified via other methods).
- **Interfaces:** REST APIs as listed in PROTOCOL.md §4; IEEE Command Search with CSV export.
- **Grey literature:** preprints (arXiv, bioRxiv), conference papers, HAL.
- **Inclusion criteria:** I1 ≥ 2 physical self-propelled or actively driven artificial agents;
  I2 behavior from agent–agent or agent–environment–agent interactions; I3 ≥ 1 quantitative
  collective or interaction observable from hardware experiments; I4 primary research (article,
  conference paper with results, preprint); I5 English, any date.
- **Exclusion criteria (precedence):** E5 not primary research; E4 biological/living matter only;
  E6 synthetic active colloids without programmable or feedback control; E1 single agent;
  E2 simulation/theory only without comparison to robotic hardware; E3 swarm-robotics engineering
  reporting only task performance.
- **Query strings:** `(active matter AND robotic agent) OR (colloid AND control) OR composite
  phrases`; exact per-source strings with run dates, counts and payload hashes in
  `protocol/search_strategies/`.
- **Search validation:** known-item recall on `protocol/search_strategies/seed_set.yml` (12/12).
- **Procedures to contact authors:** none in the first version.
- **Search expiration and repetition:** monthly re-runs; dated snapshots.

## Screening
- **Stages:** title/abstract, then full text.
- **Screeners:** three LLMs on the NHR@FAU gateway (gpt-oss-120b, Magistral-Small-2509,
  DeepSeek-V4-Flash), independent contexts, temperature 0, frozen prompt
  (`protocol/screening_prompt.md`); majority of three; R3 only where it can change the outcome.
- **Reliability:** Fleiss' and Cohen's κ; author validation on a random sample of 200 records
  (final labels: panel sensitivity 1.00, specificity 0.98, κ 0.92; blind first labels reported).
- **Reconciliation:** full-text splits and extraction conflicts argued with quotes checked against the
  full text (amendment 5) and decided by the author or, by delegation, a Claude Opus judge
  (amendment 6); author decisions always take precedence.

## Extraction
- **Entities:** platform, agents, size, propulsion, interaction, control, environment, phenomena,
  observables, theory compared and agreement, runs, data/code availability, risk of bias D1–D6.
- **Procedure:** two LLM extractors, third as arbiter for disputed fields; label-wise majority for
  multi-label fields; remaining conflicts adjudicated as above (`protocol/extraction_prompt.md`).

## Synthesis and quality assessment
- **Quality assessment:** six-domain rating (replication, agent heterogeneity, finite size and
  boundaries, measurement validity, data/code availability, quantitative theory comparison).
- **Synthesis plan:** narrative synthesis by taxonomy; evidence maps (platform × phenomenon,
  phenomenon × theory); no meta-analysis; sensitivity analyses without high-risk D1/D6 studies and
  without abstract-only assessments; certainty high/moderate/low per conclusion.
- **Data management and sharing:** all decisions, votes, extraction data and snapshots public in the
  repository (CC-BY 4.0 for text and data); subscriber full texts not redistributed.
