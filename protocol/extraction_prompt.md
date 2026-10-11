You are extracting data from ONE included study for a systematic review of ROBOTIC ACTIVE MATTER
(physical collectives of interacting, self-propelled or actively driven artificial agents).

Read the full text below and fill every field from what the paper actually reports. Never guess:
use null (or an empty list) when the paper does not state it. Use only the allowed values for
coded fields; put anything else under "other" and explain in "notes".

Fields:
- platform_class: one of "vibration_driven_robots" (bristlebots, Hexbugs, vibrobots, brainbots),
  "wheeled_or_legged_swarm_robots" (e.g. Kilobots, e-pucks, Thymio), "modular_or_self_reconfigurable_robots",
  "smarticles_or_granular_robots", "robotic_micro_nano_agents", "feedback_controlled_active_colloids",
  "robotic_metamaterial_or_active_solid", "other".
- platform_name: the device name as given (e.g. "Kilobot", "Hexbug Nano"), or null.
- n_agents_min, n_agents_max: smallest and largest number of agents used in hardware experiments (integers).
- agent_size_mm: characteristic agent size in millimetres (number), or null.
- propulsion: one of "vibration", "wheels", "legs", "magnetic_field", "light", "acoustic", "chemical", "other".
- interaction_modality: list from "steric_contact", "hydrodynamic", "magnetic", "optical_or_sensing",
  "communication", "programmed_rules", "environment_mediated", "other".
- control_architecture: one of "no_control_passive_rules", "onboard_rules", "external_feedback",
  "learned_policy", "central_controller", "other".
- environment: short free text (arena, boundaries, substrate), at most 20 words.
- phenomena: list from "flocking_polar_order", "clustering_or_mips", "swarming_or_vortex",
  "jamming_or_crystallization", "chirality_or_rotation", "active_solid_or_odd_elasticity",
  "transport_or_locomotion", "synchronization", "self_assembly_or_shape_formation",
  "boundary_accumulation", "other".
- observables: list of the quantitative observables reported (e.g. "polar order parameter",
  "pair correlation function"), at most 8 items.
- theory_compared: list from "none", "vicsek_type", "active_brownian_particles", "run_and_tumble",
  "kinetic_or_hydrodynamic_theory", "active_elasticity", "statistical_mechanics_other",
  "agent_based_simulation", "other".
- agreement: one of "quantitative", "qualitative", "none" (how theory and experiment were compared).
- n_independent_runs: number of independent experimental repetitions reported (integer), or null.
- code_available, data_available: true, false, or null (true only if a repository or archive is named).
- rob: risk-of-bias ratings, each "low", "some_concerns", or "high", with a justification of at most
  20 words: D1_replication, D2_agent_heterogeneity, D3_finite_size_and_boundaries,
  D4_measurement_validity, D5_data_code_availability, D6_quantitative_theory_comparison.
- notes: at most 40 words.

Respond with ONLY one JSON object with exactly these keys:
{"platform_class": ..., "platform_name": ..., "n_agents_min": ..., "n_agents_max": ..., "agent_size_mm": ...,
 "propulsion": ..., "interaction_modality": [...], "control_architecture": ..., "environment": ...,
 "phenomena": [...], "observables": [...], "theory_compared": [...], "agreement": ...,
 "n_independent_runs": ..., "code_available": ..., "data_available": ...,
 "rob": {"D1_replication": {"rating": ..., "why": ...}, "D2_agent_heterogeneity": {...},
         "D3_finite_size_and_boundaries": {...}, "D4_measurement_validity": {...},
         "D5_data_code_availability": {...}, "D6_quantitative_theory_comparison": {...}},
 "notes": ...}
<!-- RECORD TEMPLATE -->
Title: {title}
Year: {year}
Venue: {venue}

Full text:
{body}
