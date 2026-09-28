# Repair v0.10.0 — Imported Strategy Champion + Model Challenger Lifecycle

## Scope

v0.10.0 preserves the exact optimizer-owned parameters from the Owner-uploaded Strategy Optimizer Champion while retaining the v0.9.1 EA/runtime repairs. It then separates Model Research output from Production Champion authority.

## Imported Strategy Champion

The uploaded Champion source is provenance only; it is not copied over the newer EA implementation. The 16 Strategy Optimizer-owned input defaults are imported into the current EA so risk-cap sizing, ONNX family identity, Champion/Shadow audit CSV, and later runtime repairs remain intact.

Canonical imported geometry:

- SL ATR = `3.2`
- TP ATR = `4.8`
- Max Hold Bars = `54`

Full imported parameter evidence is stored in `EA_v1_06/CHAMPION_IMPORTED_PARAMETERS.json`. The uploaded EA did not expose the original optimizer pass ID, therefore `champion_pass` remains null rather than being invented.

## Model lifecycle

```text
Strategy Champion
      ↓
CP32 / Model Research
      ↓
ELIGIBLE_CHALLENGER
      ↓
human-readable immutable Challenger artifacts
      ↓
optional Shadow publish
      ↓
locked/fresh + deterministic promotion gates
      ↓
explicit Owner PROMOTE SELECTED CHALLENGER
      ↓
Production Model Champion
```

Model Research MUST NOT auto-promote a successful model to Champion.

## Human-readable Challenger identity

SHA-256 remains integrity evidence but is never used as the user-facing artifact name.

Examples:

- `Challenger_LSTM_20260916_223501.onnx`
- `Challenger_GRU-LightGBM_20260916_224002_Temporal.onnx`
- `Challenger_GRU-LightGBM_20260916_224002_Policy.onnx`

The compatibility aliases used by existing internal consumers may remain, but the registry, Shadow publish action, and Owner workflow use the human-readable immutable names.

## Shadow authority

Publishing a Challenger for Shadow copies its human-readable artifacts into the configured MT5 Files `models` directory. Python MUST NOT mutate the EA Challenger filename inputs. The Owner selects the Shadow Challenger by changing the EA inputs manually.

Shadow remains non-executing and cannot place or modify Champion orders.

## Champion page

The Champion page is the single model-promotion action authority. It lists registered Challengers with locked-test and available Shadow KPI evidence, exposes their human-readable artifact names, allows Shadow publish, and enables promotion only after existing deterministic promotion gates pass plus explicit Owner confirmation.

## Preserved contracts

v0.10.0 does not change:

- BUY/SKIP/SELL decision contract `[N,3]`;
- Strategy Optimizer ownership of SL/TP/MaxHold and strategy parameters;
- risk-cap sizing repair;
- Mean-R / Weighted-R optimizer accounting;
- leakage-safe temporal OOF → tree policy hybrid training;
- locked/fresh data isolation;
- Champion/Shadow trade-audit CSV separation.

## Acceptance

Local closure target: `114/114 PASS`, `first_failed_gate = null`, exact-tree signature matching `historical external: BUILD_ACCEPTANCE_v0_10_0.json`.

Real MetaEditor/MT5 compile, Shadow runtime loading, and real promotion deployment remain external gates.
