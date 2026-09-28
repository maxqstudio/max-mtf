# REPAIR v0.5.6 — ONNX opset compatibility gate

Root cause observed on Windows preflight:

- XGBoost and LightGBM conversion were requested with `target_opset=17`.
- The pinned `onnxmltools==1.16.0` converter stack reports support through opset 15 for these converters.
- Therefore preflight correctly failed before research, but the package configuration itself was incompatible.

Repair:

- deployable tabular ONNX target is now fixed to **opset 15** for XGBoost, LightGBM, and Random Forest;
- no model/research/scoring/governance logic is changed;
- preflight remains fail-closed and must still prove conversion + ONNX Runtime parity before expensive research;
- converter evidence now reports `target_opset: 15` through `converter_stack_versions()`.

Why fixed 15 instead of adding automatic retries:

A deterministic deployment contract is preferable here. Automatically trying arbitrary lower opsets would make the exported model contract dependent on which exception happened at runtime. The pinned converter stack already tells us the supported ceiling, so the package now chooses that ceiling explicitly.
