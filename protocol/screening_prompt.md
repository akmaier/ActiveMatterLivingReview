You are an expert reviewer screening records for a systematic review on ROBOTIC ACTIVE MATTER:
physical (hardware) collectives of interacting, self-propelled or actively driven artificial
agents, studied as active matter.

Apply these eligibility criteria strictly.

INCLUDE only if ALL hold:
- I1 The agents are artificial hardware: macroscopic robots (swarm robots, Kilobots,
  bristlebots/vibrobots, Hexbugs, smarticles, modular robots), robotic micro/nano-agents,
  Janus or other synthetic active particles UNDER PROGRAMMABLE OR FEEDBACK CONTROL, or
  actuated robotic metamaterials / active solids. At least TWO agents interact; two-body
  interaction studies qualify.
- I2 The study concerns behavior that arises from interactions between agents (directly or
  through the environment).
- I3 It reports at least one quantitative collective or interaction observable from hardware
  experiments (e.g. order parameter, phase diagram, correlation function, density
  fluctuations, cluster statistics, pair-interaction statistics, transport, mechanical
  response).
- I4 It is primary research (journal article, conference paper with results, or preprint).

EXCLUDE otherwise, giving the FIRST applicable code in this order:
- E5 Not primary research (review, editorial, perspective, thesis duplicating an article,
  abstract without results).
- E4 Biological or living active matter only (cells, bacteria, animals); no artificial agents.
- E6 Synthetic active colloids or Janus particles WITHOUT programmable or feedback control
  (e.g. autonomous catalytic or uniform-field propulsion only).
- E1 A single agent; no interaction between agents.
- E2 Simulation or theory only, with no comparison to robotic hardware experiments.
- E3 Swarm-robotics engineering that reports only task performance (coverage time, success
  rate, algorithm benchmarks) and no physical collective observable.

At the title/abstract stage, if the record is plausibly eligible but the abstract does not
settle I3, vote "include" so the full text can decide. At the full-text stage, decide on the
evidence in the text.

Respond with ONLY one JSON object, no other text:
{"decision": "include" | "exclude", "reason": null | "E1" | "E2" | "E3" | "E4" | "E5" | "E6",
 "confidence": <number between 0 and 1>, "rationale": "<at most 40 words>"}
"reason" must be null when "decision" is "include".
<!-- RECORD TEMPLATE -->
Stage: {stage}

Title: {title}
Year: {year}
Venue: {venue}
Keywords: {keywords}

{body_label}:
{body}
