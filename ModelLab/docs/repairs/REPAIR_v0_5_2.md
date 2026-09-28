# v0.5.2 ONNX Export Hardening

This revision is based on v0.5.1 Adaptive Supervisor and keeps the research/search/governance logic unchanged.

Repairs:

- XGBoost and LightGBM use `onnxmltools.convert.common.data_types.FloatTensorType`.
- Random Forest uses `skl2onnx.common.data_types.FloatTensorType`.
- LightGBM conversion now explicitly sets `zipmap=False`; the default map output is incompatible with the EA `[1,3]` `vectorf` contract.
- Class order is fail-closed and must be exactly `[0,1,2] = [SELL,SKIP,BUY]`.
- ONNX input/output type, rank, feature count, class count, finite values, probability sums and runtime parity are validated.
- Export writes atomically through a temporary file.
- Converter preflight now runs only enabled model families and persists `historical external: onnx_preflight.json` including package versions and per-family PASS/FAIL.
- A failed converter blocks research before expensive walk-forward training.
- Converter-critical Python packages are pinned to one reproducible v0.5.2 stack.
- `ModelLab/tools/maintenance/RESET_ENV.cmd` is included to rebuild `.venv` without PowerShell.

No change to CP32 features, forward-label policy, walk-forward/locked-test rules, adaptive Supervisor search, LLM Scientist authority, or Champion governance.
