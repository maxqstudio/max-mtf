# ONNX + Decision Policy Contract · EA v1.06

## Class order

Final policy output is always:

```text
0 SELL
1 SKIP
2 BUY
```

Hybrid temporal output is:

```text
0 DOWN
1 UP
```

## CP32 tabular

```text
input  float32 [1,32]
output float32 [1,3]
sequence_length = 1
```

## CP32 standalone temporal GRU

```text
input  float32 [1,T,32]
output float32 [1,3]
T = frozen hyperparameters.sequence_length
```

## CP32 hybrid GRU → classical

Temporal stage:

```text
input  float32 [1,T,32]
output float32 [1,2]   # DOWN, UP
```

Meta-feature stage:

```text
policy[0:32] = CP32 current feature row
policy[32]   = P(DOWN)
policy[33]   = P(UP)
policy[34]   = P(UP) - P(DOWN)
policy[35]   = max(P(DOWN), P(UP))
```

Policy stage:

```text
input  float32 [1,36]
output float32 [1,3]   # SELL, SKIP, BUY
```

The Python policy is trained on **out-of-fold temporal probabilities**. In-sample GRU predictions must never be used to train the classical meta-policy.

## Causal warmup/context

For temporal inference, missing prehistory is left-padded with the oldest available CP32 row. During validation, Python supplies authorized rows before the target fold as causal context; it does not rebuild the fold as if history began at validation start. EA rolling history follows the same rule.

## Decision/risk authority

`CP_POLICY_V1`/model probabilities choose or filter trade direction/opportunity. Position size, SL/TP, max hold, spread limits and daily drawdown limits remain deterministic EA authority.

## Parity boundary

A hybrid Challenger requires parity of both `*_temporal.onnx` and `*_policy_model.onnx`. Package-local source tests validate the contract logic, but actual ONNX Runtime and MT5 runtime parity remain explicit Owner-machine gates.


## v0.9.1 ONNX family + audit CSV

Supported runtime family identities: LightGBM, XGBoost, RandomForest, GRU, LSTM, TCN, Transformer Encoder, PatchTST, iTransformer, TFT, Transformer MoE. Hybrid runtime is generic temporal→tree policy. `Max_Champion_Trades.csv` contains actual MT5 deal evidence; `Max_Shadow_Trades.csv` contains non-executing Challenger entry candidates (`executed=0`). These ledgers are audit-only and do not own optimizer fitness or live execution authority.
