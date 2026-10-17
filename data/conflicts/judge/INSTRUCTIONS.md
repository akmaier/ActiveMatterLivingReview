# Instructions for the Opus judge (protocol amendment 6)

You are the judge for conflicts in a PRISMA 2020 systematic review of ROBOTIC ACTIVE MATTER.
The author delegated these conflicts to you. Three LLM reviewers (R1 gpt-oss-120b,
R2 Magistral-Small, R3 DeepSeek-V4-Flash) disagreed. Each one argued its answer with quotes from
the paper. Every quote was checked automatically against the full text:
`verbatim`, `close` (nearly verbatim), `partial` (partly in the text) or `not_found`
(treat it as unsupported).

Decide each item on the evidence. Weigh the checked quotes, not the reviewers' confidence or
the majority. When the quotes conflict or are insufficient, open `full_text_file` (read-only)
and search it (grep for robot counts, "experiment", "hardware", "simulation", the field in
question). Never modify any file in the repository except your own output file.

## Eligibility (full-text splits)
- I1 >= 2 physical self-propelled or actively driven artificial agents (two-body studies qualify).
- I2 Behavior arising from agent-agent or agent-environment-agent interactions.
- I3 >= 1 quantitative collective or interaction observable from HARDWARE experiments.
- I4 Primary research article, conference paper with results, or preprint.
- Exclusion codes, in order of precedence (assign the FIRST that applies):
  E5 not primary research (review, editorial, perspective, thesis duplicating a journal article,
  abstract without results); E4 biological or living active matter only; E6 synthetic active
  colloids or Janus particles without programmable or feedback control; E1 single agent;
  E2 simulation or theory only, with no comparison to robotic hardware experiments;
  E3 swarm-robotics engineering reporting only task performance (coverage time, success rate,
  benchmarks) with no physical collective observable.
- Records marked `abstract_only: true` have no obtainable full text; judge on the abstract
  (the full_text_file then holds only the abstract).

## Extraction conflicts
Pick the value the paper supports for each field. You may choose a reviewer's value or give your
own. Use the vocabulary given in `vocab` where there is one. Counts are integers. Use null when
the paper does not report the value. Risk-of-bias ratings are low / some_concerns / high.

## Output
Write ONE JSON object per line (JSONL) to the output file named in your task, appending as you go
so that partial progress survives:
- full-text split:
  {"queue": "ft_split", "record_id": "...", "include": true|false, "reason": "E1".."E6"|null,
   "rationale": "<= 40 words naming the decisive evidence", "consulted_full_text": true|false}
- extraction field:
  {"queue": "extraction", "record_id": "...", "field": "...", "value": <value>,
   "chosen_from": "R1"|"R2"|"R3"|"judge", "rationale": "<= 30 words",
   "consulted_full_text": true|false}
Cover EVERY item (and every field) in your batch. If you truly cannot decide, write
"include": null (or "value" omitted) with a rationale; the author will see it.
When finished, reply with counts only: items decided, includes/excludes (or fields set),
undecided, and how many required the full text.
