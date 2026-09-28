# CPMF v0.7.5 R6 Repair1 — Hybrid Capacity + Resource Preflight

## Trigger
Post-seal Control Room audit reproduced three defects not covered by the original 68-gate suite:
1. dynamic hybrid component bounds could be wider than the same standalone family safe envelope;
2. Scientist/Director envelope proposals could replace a deterministic fallback instead of being intersected with it;
3. `safe_ram_fraction`, `safe_vram_fraction`, and `max_single_experiment_minutes` were persisted/reportable but were not executable candidate hard gates.

## Repair
- Dynamic hybrids now compose `temporal_*` and `policy_*` ranges from the exact base-family dataset/hardware recommended envelopes.
- Shared `training_memory_months` is the intersection of temporal and policy safe recommendations.
- `_intersect_envelope()` is now a true fail-closed intersection. Generation review may move within the original frozen safe envelope but cannot reopen it.
- Research plans freeze `resource_capacity` with hardware snapshot, Owner limits, dataset row reference, and WFA fold count.
- `candidate_capacity_contract()` V2 evaluates parameter-count plus estimated peak RAM, estimated peak VRAM where applicable, and estimated total WFA runtime before training.
- Tree candidates are covered by RAM/time resource authority; neural/hybrid candidates additionally cover temporal parameter count and accelerator VRAM where applicable.
- Added adversarial gates `R14_HYBRID_COMPONENT_CAPACITY_ENVELOPE_PARITY` and `R14_RESOURCE_PREFLIGHT_HARD_BUDGETS`.
- Package metadata family name corrected from `randomforest` to canonical `random_forest`.

## Acceptance
Full cumulative suite: **70 / 70 PASS**, `first_failed_gate = null`.

External Owner-machine gates remain NOT RUN here: real CUDA training, real Transformer-family ONNX Runtime parity, MetaEditor compile, and MT5 tester/runtime.
