# v0.5.1 ONNX Converter Repair

## Defect reproduced from v0.4.2 evidence

Final XGBoost export failed with:

`XGBClassifier ... wrong type onnxconverter_common.data_types.FloatTensorType; only onnxmltools.convert.common.data_types.FloatTensorType / Int64TensorType allowed`

## Root cause

`ModelLab/models/onnx_export.py` created one generic `FloatTensorType` from `onnxconverter_common` and passed it to all converter families. `onnxmltools` XGBoost/LightGBM shape calculators perform type checks against their own converter namespace, so the identically named class is not interchangeable.

## Repair

Family-specific converter contracts are now explicit:

- XGBoost: `onnxmltools.convert.common.data_types.FloatTensorType`
- LightGBM: `onnxmltools.convert.common.data_types.FloatTensorType`
- Random Forest: `skl2onnx.common.data_types.FloatTensorType`

The generic `onnxconverter_common.data_types.FloatTensorType` import was removed.

## New fail-early gate

Before expensive research begins, Supervisor now trains tiny synthetic 3-class models for all three deployable families, converts each to ONNX, opens it with ONNX Runtime, and checks native-vs-ONNX probability parity at tolerance `1e-4`.

Artifact: `historical external: onnx_preflight.json`

If converter compatibility is broken, research stops immediately instead of failing only after all walk-forward experiments have finished.

## Scope

No changes to:
- feature contract CP32,
- label policy,
- walk-forward selection,
- Adaptive Supervisor search,
- locked-test governance,
- Champion promotion authority.
