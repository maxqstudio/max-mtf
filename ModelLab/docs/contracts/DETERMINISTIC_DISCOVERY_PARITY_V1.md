# Deterministic Discovery Parity V1 — CPMF v0.7.5 R4

## Purpose

R4 makes deterministic Discovery a first-class research engine rather than an old-model fallback behind the LLM Scientist. LLM proposals remain optional research hypotheses. Candidate legality, topology allocation, capacity, chronology/leakage, deduplication, fidelity promotion, KPI authority and downstream PASS/FAIL remain deterministic.

## Deterministic candidate flow

`Registry → Owner allowed universe → hardware feasibility → dataset capacity → topology allocation → candidate admission → Cheap Screen → topology/family-aware promotion → Full WFA → Pool → CPCV seed confirmation → downstream stages`

### Registry-driven no-LLM Discovery

When Scientist does not provide an executable plan, deterministic planning uses all Owner-permitted, hardware-feasible base families from the current model registry. It does not fall back to the historical LightGBM/XGBoost/TCN/GRU shortlist.

Round 1 is stratified/space-filling. Later rounds use committed research evidence for bounded adaptive search.

### Candidate Admission Compiler

LLM, deterministic, memory-derived and fallback proposals are all subject to the same deterministic admission rules:

- Owner Single↔Hybrid allocation remains authority.
- family and dynamic-hybrid compatibility must be registry-valid.
- parameter values must be legal and canonicalized.
- effective duplicate configurations are rejected.
- temporal/hybrid parameter count must fit the compiled capacity contract before training.

The LLM cannot redefine a 50/50 Owner topology request by returning an imbalanced proposal batch.

### Fidelity allocation

Cheap Screen remains resource allocation only. Full WFA is the Discovery qualification authority.

Promotion to Full WFA preserves the configured Single↔Hybrid opportunity and prefers distinct families before duplicate-family fills. This prevents a global Cheap-Screen leaderboard from silently converting an Owner 50/50 research allocation into all-Single or all-Hybrid Full-WFA evidence.

### Effective-parameter identity

Search identity removes shadow/no-op dimensions where a more specific executable parameter owns the actual architecture, including `hidden_size` when `d_model` or `tcn_channels` is authoritative. Fingerprints therefore represent effective executable configurations rather than syntactic parameter noise.

### Capacity authority

The dataset/hardware capacity governor emits preferred and extended parameter bands. R4 semantics:

- preferred band: search guidance, not a PASS gate;
- extended band: larger-capacity search region available only while the candidate remains inside the dynamic LEGAL/RESOURCE/SCIENTIFIC hard ceilings;
- candidates above that ceiling fail admission with `MODEL_PARAMETER_COUNT_EXCEEDS_EXTENDED_CAPACITY`.

Actual executable parameter count is used, including the temporal leg of a dynamic hybrid.

### Risk-aware deterministic ranking

The WFA ranking score remains subordinate to hard acceptance, but now includes all enabled Advanced risk KPIs used by current governance: Sharpe, Sortino, Calmar/MAR, PSR, DSR, Ulcer and CVaR/ES. The composite remains normalized to a 100-point scale for longitudinal comparability.

Family learning uses robust evidence (PASS rate, median, lower-quartile score, near-miss margin and exploration) instead of a single lucky best score.

### Threshold and multiplicity control

A candidate's WFA acceptance/ranking is graded with leave-one-WFA-fold-out threshold selection: each held fold is evaluated using a threshold selected from the other folds. A final deployment threshold is then selected from all authorized WFA evidence and frozen for downstream CPCV.

DSR trial budget now accounts for model-candidate budget, take-threshold search multiplicity and bounded policy-search multiplicity.

## CPCV seed robustness

Temporal standalone and temporal→ML hybrid finalists require progressive confirmation using the predeclared fixed seed set:

`42 → 11 → 77`

All seeds use the same candidate parameters, CPCV partitions, purge/embargo and frozen take threshold. Only training initialization changes.

- 3/3 PASS is required.
- A failed seed stops additional confirmation compute immediately.
- Tree-only candidates remain fixed-seed by default.
- The final CPCV evidence records planned/completed seeds and a mandatory `CPCV_SEED_STABILITY` gate.

This tests initialization robustness without multiplying all Discovery compute by three.

## Preserved authority

R4 does not weaken WFA/CPCV/Tournament/Monte-Carlo/Forward hard gates. Scientist cannot override deterministic PASS/FAIL. Locked/fresh Forward remains protected from repeated tuning.


## R6 per-family model-size priority
Every base model family has a frozen Owner `Small 0.00 ↔ 1.00 Large` search preference. It biases deterministic generation but does not hard-slice executable bounds. Temporal and temporal-hybrid candidates are admitted by actual executable parameter count under the shared dynamic `min(LEGAL, RESOURCE, SCIENTIFIC)` authority.
