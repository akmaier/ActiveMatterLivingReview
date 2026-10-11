# Eligibility criteria (PECO for engineered systems)

Status: **DRAFT** (scope questions resolved 2026-10-11; freezes with the protocol).

| Element | Definition |
|---|---|
| **Population** | Physical (hardware) collectives of **≥ 2** interacting self-propelled or actively driven artificial agents: macroscopic robots (swarm robots, Kilobots, bristlebots/vibrobots, Hexbugs, smarticles, modular robots), robotic micro/nano-agents, Janus or other synthetic active particles **only when under programmable or feedback control**, actuated robotic metamaterials / active solids. |
| **Exposure** | Interactions among agents (contact, hydrodynamic, sensing/communication, programmed rules) and their control parameters. |
| **Comparator** | Optional: theory, simulation, passive counterparts, or other parameter regimes. |
| **Outcome** | At least one quantitative collective-behavior or interaction observable (order parameter, phase diagram, correlation function, density fluctuations, cluster statistics, pair-interaction statistics, transport, mechanical response). |
| **Study design** | Primary experimental studies. Theory/simulation studies only if they compare quantitatively to robotic experimental data. |

## Inclusion

- I1 Population as above; two-body interaction studies qualify.
- I2 Reports behavior arising from agent–agent or agent–environment–agent interactions.
- I3 Reports ≥ 1 quantitative collective or interaction observable from hardware experiments.
- I4 Primary research article, conference paper with results, or preprint.
- I5 English; any publication date.

## Exclusion (codes listed in order of precedence)

When several apply, the record is assigned the first applicable code, so the PRISMA flow
reports exactly one reason per excluded report.

- **E5** Not primary research: reviews, editorials, perspectives, theses duplicating a
  journal article, abstracts without results. (Reviews are mined for citation chasing.)
- **E4** Biological or living active matter only (cells, bacteria, animals), no artificial agents.
- **E6** Synthetic active colloids or Janus particles without programmable or feedback
  control (e.g. autonomous catalytic or uniform-field propulsion only).
- **E1** Single agent: one robot or particle, no interaction between agents.
- **E2** Simulation or theory only, with no comparison to robotic hardware experiments.
- **E3** Swarm-robotics engineering reporting only task performance (coverage time, success
  rate, algorithm benchmarks) with no physical collective observable.

## Decisions taken (2026-10-11)

1. Synthetic active colloids: excluded in general; Janus/synthetic active particles are
   included only under programmable or feedback control (E6).
2. Agent threshold: ≥ 2; two-body interaction studies count, single-agent studies do not (E1).
3. Swarm-robotics engineering papers: excluded unless they report a physical observable (E3).
4. Reviewers: a panel of three LLMs on the NHR@FAU gateway (see `PROTOCOL.md` §6).
