# Transformer Family Research V1 — CPMF v0.7.5 R2

## Executable family universe

CPMF now keeps five Transformer-derived alternatives as **research competitors**, not upgrades by assumption:

1. **Transformer Encoder** — vanilla causal encoder and scientific control.
2. **PatchTST** — CPMF multivariate causal-patch adaptation. Historical CP32 windows are compressed into chronological patch tokens; the final patch always terminates on the current bar.
3. **iTransformer** — inverted variable-token encoder. Each CP32 feature becomes a token representing its historical lookback; attention is across variables, never future bars.
4. **TFT** — observed-covariate adaptation with variable selection, recurrent local processing and causal attention. CPMF does not fabricate static or known-future covariates that are absent from the CP32 contract.
5. **Transformer MoE** — experimental learned Top-K expert specialization.

TCN, GRU, LSTM and tree models remain controls. The Scientist must justify extra complexity using committed WFA/CPCV evidence.

## Capacity authority

Dataset Capacity Profile and hardware profile generate conservative starting envelopes. They are research priors, not profitability gates. For the Owner's expected ~35k H1 history / ~10k bars per fit, the preferred total-parameter band remains small by deep-learning standards; the Scientist should first test compact variants.

## Dynamic hybrids

All three new temporal families participate in the existing grammar `hybrid::<temporal>::<policy>`, including `PatchTST → LightGBM`, `iTransformer → LightGBM`, and `TFT → LightGBM`. OOF temporal-direction stacking, chronology protection and deterministic EA risk authority are unchanged.

## Deployment caveat

Python train/predict/runtime contracts are acceptance-tested in this build. ONNX converter/runtime parity for PatchTST/iTransformer/TFT must still be executed on the Owner Windows environment because the build container does not contain `onnx`/`onnxruntime`. MT5 compile/runtime authority is likewise Owner-machine acceptance.
