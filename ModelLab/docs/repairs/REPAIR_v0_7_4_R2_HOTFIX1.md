# CPMF v0.7.4 R2 Hotfix1 — Windows ONNX Artifact Path

## Runtime defect

Factory ONNX preflight failed on Windows before Discovery:

```text
hybrid::gru::lightgbm_temporal.onnx.tmp
OSError: [Errno 22] Invalid argument
```

The dynamic hybrid family ID is a valid canonical research identity but `:` is invalid in Windows filename components.

## Repair

- Added central `artifact_paths.filesystem_safe_id()` for filesystem boundaries.
- Canonical family IDs remain unchanged in registry, research plan, Scientist context, lineage, and evidence.
- `export_hybrid()` now writes filesystem-safe artifact names only.
- ONNX preflight standalone artifact naming also uses the central sanitizer.
- Added `ModelLab/tests/windows_artifact_path_selftest.py` for GRU/TCN/LSTM/Transformer hybrid IDs and Windows reserved/invalid filename rules.
- Included the latest UI-only compact sidebar Research lifecycle control.

## Acceptance

Cumulative local acceptance: **50/50 PASS**, `first_failed_gate = null`.
External Owner-machine ONNX runtime parity / MetaEditor / MT5 gates remain external.
