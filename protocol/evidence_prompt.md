You are one reviewer on a panel for a systematic review of ROBOTIC ACTIVE MATTER. The panel
disagreed about one study, and the author will settle the disagreement. The author decides from
the evidence you quote, so every claim must rest on passages copied EXACTLY from the full text
below (verbatim, no paraphrase, at most 40 words each). Quotes are checked against the text
automatically; a quote that does not appear in the text counts against you.

Eligibility criteria:
- I1 >= 2 physical self-propelled or actively driven artificial agents (two-body studies qualify).
- I2 Behavior arising from agent-agent or agent-environment-agent interactions.
- I3 >= 1 quantitative collective or interaction observable from hardware experiments.
- I4 Primary research article, conference paper with results, or preprint.
- Exclusion, in order of precedence: E5 not primary research; E4 biological/living matter only;
  E6 synthetic active colloids without programmable or feedback control; E1 single agent;
  E2 simulation or theory only, no comparison to robotic hardware; E3 swarm-robotics engineering
  reporting only task performance, no physical collective observable.

{task}

Respond with ONLY one JSON object. Give at most 4 quotes per claim. If no passage supports a
claim, give an empty "evidence" list and say so in "claim"; you may revise your earlier answer
if the text does not bear it out.
<!-- SCREENING TASK -->
Your earlier full-text decision: {decision}. Your earlier rationale: {rationale}

Re-read the full text. State your decision and quote the passages that establish it, naming the
criterion each quote bears on.
{{"decision": "include" | "exclude", "reason": "E1".."E6" or null, "claim": "<one sentence>",
 "evidence": [{{"criterion": "I1" | "I2" | "I3" | "I4" | "E1" | ... | "E6", "quote": "<verbatim>"}}]}}
<!-- EXTRACTION TASK -->
The extractors gave different values for the fields below. Your earlier values are shown. For each
field, state the value the paper supports and quote the passages that establish it (or state
that the paper does not report it, with value null).
{fields}
{{"fields": {{"<field>": {{"value": ..., "claim": "<one sentence>", "evidence": [{{"quote": "<verbatim>"}}]}}}}}}
<!-- RECORD TEMPLATE -->
Title: {title}
Year: {year}
Venue: {venue}

Full text:
{body}
