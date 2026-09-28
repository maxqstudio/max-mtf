# CPMF v0.7.3 R5 — Scientific Research Engine V3

## Scope

R2 implements the second v0.7.3 workflow step without changing model families, labels, KPI thresholds, Research Kernel V2 chronology, or CPCV/Tournament/Monte-Carlo/Forward authority.

The purpose is to spend CPU on promising proposals while preserving a strict distinction between **research diagnostics** and **qualification authority**.

## Canonical Discovery flow

`Proposal → Cheap Screen → promoted subset → Full WFA → WFA PASS → Pool 12 → CPCV Finalists → Tournament → Monte Carlo → Forward Championship → Champion`

### Level 1 — Cheap Screen

- chronological WFA only;
- fewer folds than full WFA;
- training-resource knobs only are reduced (`n_estimators`, policy trees, GRU epochs);
- label, feature schema, training memory, architecture width/depth, thresholds, purge/embargo and scientific CandidateSpec remain unchanged;
- a Cheap Screen PASS **does not qualify** a candidate;
- screen evidence is diagnostic and resource-allocation evidence only.

### Level 2 — Full WFA

Promoted candidates are re-run from their original CandidateSpec under the complete configured WFA contract. Only `walk_forward_acceptance()` on this full run may add a candidate to Pool 12.

Default R2 CPU policy:

- cheap folds: 2;
- cheap training-resource scale: 0.50;
- promote fraction: 0.33;
- minimum promotions per round: 2;
- maximum promotions per round: 3.

These values are resource policy, not trading KPI.

## Failure Margins

Every full-WFA hard gate keeps its normal binary PASS/FAIL authority. R2 additionally records a **Failure Margin**:

- positive/zero margin = threshold met;
- negative margin = shortfall;
- closest failed gate = nearest hard failure;
- deepest failed gate = largest normalized shortfall.

Failure Margins are diagnostic only. They are never summed to rescue a failed candidate and never alter a KPI threshold.

## Failure Topology

R2 aggregates:

- first failed gate counts;
- all failed gate counts;
- failure-group counts;
- family-specific failure patterns;
- near-miss candidates.

Two topologies are deliberately separated:

1. `historical external: screen_failure_topology.json` — cheap-screen diagnostic evidence;
2. `historical external: failure_topology.json` — full-WFA research evidence.

The Research Director receives full-WFA topology as the primary scientific bottleneck state. Cheap-screen topology is explicitly marked non-authoritative.

## All-Trial Ledger

Every proposal is retained, including candidates discarded by the cheap screen.

Per Supervisor run:

- `all_trials.jsonl`
- `historical external: all_trial_summary.json`
- `historical external: screen_leaderboard.json`
- `historical external: cv_leaderboard.json`
- `historical external: screen_failure_topology.json`
- `historical external: failure_topology.json`

At Factory level, per-generation ledgers are merged into an append-stable `all_trials.jsonl`. Resume de-duplicates committed records by source run / stage / round / candidate identity.

This prevents losing negative evidence and makes later Experiment Blocks / hypothesis lifecycle auditable.

## Fail-closed rules

- Cheap Screen never grants WFA PASS.
- Full WFA still uses existing hard KPI gates unchanged.
- CPCV remains outside Discovery and opens only after frozen Pool 12.
- Failure Margin cannot compensate a failed gate.
- Failure Topology cannot promote a candidate.
- LLM Director/Scientist can read diagnostics but cannot alter KPI authority.
- Locked Tournament/Monte-Carlo/Forward evidence remains outside active Discovery Research Memory.

## Deferred to later v0.7.3 revisions

R3: Experiment Blocks, hypothesis lifecycle, bounded Director directives and falsification/retirement rules.

R4: local CPU calibration/resource scheduler and adversarial leakage CI.

No TCN, MiniROCKET, HMM, Transformer, larger GRU family, new trading KPI, or relaxed acceptance threshold is introduced in R2.


## R3 — Experiment Blocks and hypothesis lifecycle

R3 changes the unit of directed research from an unstructured stream of candidates into a bounded Experiment Block. A block has one active hypothesis, one anchor model, an explicit budget, variable dimensions, frozen dimensions and a falsification rule. Non-variable parameters are frozen to the anchor before candidate validation, preventing a hypothesis test from silently changing unrelated knobs.

Lifecycle states are `PROPOSED → ACTIVE → SUPPORTED | FALSIFIED | INCONCLUSIVE`; supported ideas may later be EXTEND/EXPLOIT, while failed ideas can be retired. `historical external: hypothesis_lifecycle.json`, `historical external: active_experiment_block.json`, and `historical external: experiment_block_outcome.json` are persisted per run and carried through Factory Research Memory. These states are research evidence only; Full WFA remains the sole Discovery qualification authority.


## R4 — CPU resource calibration and adversarial leakage CI

R4 completes the planned v0.7.3 engine. `ModelLab/host/cpu_resource.py` calibrates a conservative model-thread count once per physical-core identity, persists it, and enforces outer trial concurrency = 1 so HPO and learner parallelism do not multiply each other. The calibration is a lightweight local proxy, not a performance guarantee; actual fit times continue to be logged by model trials.

`ModelLab/data/leakage_adversarial_ci.py` adds executable chronology, label-overlap, sequence-discontinuity and future-perturbation checks. The acceptance selftest injects a deliberately leaky future-shifted feature and requires the perturbation detector to FAIL it. A detector that cannot reject the injected leak fails the release gate.

## R5 Scientist-to-Experiment execution contract

A failure-learning plan is considered ready only when it contains an objective, concrete changes, falsification condition, and at least one mechanism wired into next Discovery. `MODEL_ARCHITECTURE` hypotheses may declare `parameter_ranges_by_family`; the Experiment Block remaps generated candidates into those bounded ranges while freezing unrelated dimensions to its anchor. `TRAINING_MEMORY` enforces its declared windows. `SELECTIVITY_POLICY` updates the actual deployment threshold grid used by Full WFA.

Hybrid LightGBM/XGBoost policy regularization (`policy_reg_alpha`, `policy_reg_lambda`) is now part of the legal registry. LightGBM row subsampling explicitly activates bagging frequency so `subsample < 1` is not a no-op.
