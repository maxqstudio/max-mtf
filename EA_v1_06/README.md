# ComplexPolicy EA v1.06

EA v1.06 keeps the first-write-wins CSV/gap-fill contract and adds runtime support for both standalone temporal GRU and two-stage hybrid GRU→classical policy inference.

## Training-data writer

- Identity: `(contract, symbol, period, signal_time)`.
- Cooperating v1.06 writers serialize through the writer lock and use **first-write-wins**.
- Existing live rows are preserved.
- An overlapping Strategy Tester run appends only physically missing H1 timestamps, so it can fill collection gaps without duplicating or overwriting live evidence.
- The EA preloads a sorted timestamp index and refreshes appended tail rows before each write.
- Do not keep a legacy non-cooperating writer active against the same CSV.

## Runtime model modes

### Tabular classical

```text
float32 [1,32] -> [1,3]
SELL / SKIP / BUY
```

Set the corresponding standalone sequence length to `1`.

### Standalone GRU

```text
float32 [1,T,32] -> [1,3]
SELL / SKIP / BUY
```

`T` is frozen by the candidate manifest (research range 8–24 H1 bars).

### Hybrid GRU → classical policy

Temporal model:

```text
float32 [1,T,32] -> [1,2]
DOWN / UP
```

EA builds the classical policy input in exact order:

```text
CP32[0..31]
p_down
p_up
p_up - p_down
max(p_down,p_up)
```

Policy model:

```text
float32 [1,36] -> [1,3]
SELL / SKIP / BUY
```

Champion and Challenger each have independent standalone/hybrid flags and sequence lengths.

## Risk authority

Hybrid model output does **not** own capital risk. EA inputs and deterministic execution remain authoritative for:

- `InpRiskPct`;
- `InpSL_ATR`;
- `InpTP_ATR`;
- `InpMaxHoldBars`;
- `InpMaxSpreadPoints`;
- `InpMaxDailyLossPct`;
- position sizing and execution gates.

## External acceptance

This package does not claim a MetaEditor compile or real MT5 ONNX execution. Compile v1.06 and follow `historical external: ../OWNER_RUNTIME_ACCEPTANCE_v0_6_6.md`.


## v0.9.1 ONNX family + audit CSV

Supported runtime family identities: LightGBM, XGBoost, RandomForest, GRU, LSTM, TCN, Transformer Encoder, PatchTST, iTransformer, TFT, Transformer MoE. Hybrid runtime is generic temporal→tree policy. `Max_Champion_Trades.csv` contains actual MT5 deal evidence; `Max_Shadow_Trades.csv` contains non-executing Challenger entry candidates (`executed=0`). These ledgers are audit-only and do not own optimizer fitness or live execution authority.
