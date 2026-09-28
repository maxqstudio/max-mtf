# Topology Priority + Decision Contract V1 — CPMF v0.7.5 R3

## Owner topology authority

`research_architecture.hybrid_priority` is a bounded scalar in `[0.00, 1.00]`:

- `0.00` = 100% standalone/single candidates
- `0.50` = 50% standalone + 50% hybrid candidates
- `1.00` = 100% hybrid candidates

The value controls **candidate-count allocation**, not prediction blending. The compiled Factory research plan freezes the value under `topology_priority`; a running Factory therefore cannot silently change semantics when the UI changes later.

Scientist chooses families, hyperparameter envelopes, and compatible hybrid compositions inside the Owner allocation. It may recommend a future slider change but cannot override the persisted allocation.

`historical external: supervisor_plan.json` records configured priority, target/actual SINGLE and HYBRID candidate counts, constraint state, and a separate estimated compute-time share. Candidate share and compute share are intentionally not treated as the same quantity.

## Final decision contract

Every executable standalone or hybrid candidate converges to the same final schema:

`[P(SELL), P(SKIP), P(BUY)]` = `[N,3]`, canonical classes `0/1/2`.

`models.normalize_final_decision_proba()` aligns estimators that expose a bounded subset of classes into the canonical three-column schema. This keeps evaluation rows, timestamps, action mapping, and downstream KPI authority comparable across architectures.

### Standalone temporal

`CP32 sequence -> temporal model -> neural decision head -> SELL/SKIP/BUY`.

Standalone GRU/LSTM/TCN/Transformer/PatchTST/iTransformer/TFT/Transformer-MoE therefore own a direct 3-class prediction head during research evaluation.

### Hybrid temporal -> policy

`CP32 sequence -> temporal direction model -> [P(DOWN),P(UP)] -> 4 meta-features -> CP32+4 -> ML policy -> SELL/SKIP/BUY`.

The four meta-features are fixed:

1. `P(DOWN)`
2. `P(UP)`
3. `P(UP)-P(DOWN)`
4. `max(P(DOWN),P(UP))`

Training uses purged/index-preserving OOF temporal predictions for the policy leg. The policy never trains on in-sample temporal predictions. Final deterministic risk/execution authority remains outside model authority.

## Comparison rule

Standalone and hybrid are comparable only when they share:

- source snapshot / row authority
- chronological split and target timestamps
- SELL/SKIP/BUY label authority
- final `[N,3]` class order
- deterministic TAKE/direction/execution gates
- WFA/CPCV/KPI acceptance contract

Their probability values are **not expected to be equal**. The purpose of research is to test whether one topology generalizes more robustly than the other.
