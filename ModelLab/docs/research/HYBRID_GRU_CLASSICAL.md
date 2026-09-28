# Hybrid GRU → Classical Policy · v0.6.6

## Purpose

The hybrid family separates temporal direction detection from opportunity selection and capital risk.

```text
causal H1 CP32 sequence
    -> GRU direction model
    -> P(DOWN), P(UP)
    -> CP32 + temporal meta-features
    -> XGBoost / LightGBM / RandomForest policy
    -> SELL / SKIP / BUY
    -> deterministic EA risk/execution
```

## Leakage prevention

The classical policy is **not** trained on GRU predictions from a GRU that saw the same target row. `HybridStackClassifier` creates chronological inner folds, trains a temporary direction GRU on each past-only training segment, and predicts the following validation segment. Only these OOF predictions are eligible as policy meta-features.

After the OOF classical policy is fitted, the deployable direction GRU is refitted on the full authorized training window. Locked/fresh validation remains outside that fit.

## Temporal context

Validation prediction uses authorized pre-fold CP32 rows as sequence context. No future row is used, and fold-local left padding is not substituted when genuine earlier history exists.

## Meta features

Exact policy input order:

```text
0..31  CP32 current row
32     P(DOWN)
33     P(UP)
34     P(UP)-P(DOWN)
35     max(P(DOWN),P(UP))
```

## Search staging

- Initial discovery excludes hybrid families.
- When non-hybrid families are enabled, hybrid families may use staged cost-aware unlock after standalone GRU evidence. In **hybrid-only mode**, all enabled hybrid families are first-class research families immediately; standalone GRU is not required.
- Hybrid temporal parameters are seeded from the best available standalone GRU with bounded jitter **when such evidence exists**; otherwise each hybrid searches its own bounded GRU temporal parameters.
- Default `hybrid_max_per_round = 2` limits expensive stacked fits.
- GRU→XGBoost and GRU→LightGBM are enabled by default; GRU→RandomForest is optional.

This compute gate does not bypass or relax any KPI gate.

## Runtime artifacts

Hybrid export produces:

```text
challenger_temporal.onnx     [1,T,32] -> [1,2]
challenger_policy_model.onnx [1,36]   -> [1,3]
```

The manifest freezes `T`, file hashes and `CP_HYBRID_GRU_CLASSICAL_V1` runtime contract.

## Risk authority

Neither GRU nor the classical policy may directly set account risk. EA v1.06 retains deterministic authority for risk percentage, sizing, SL/TP ATR, max holding bars, spread limits and daily drawdown guard.
