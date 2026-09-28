# v1.02 Training Export Patch

v1.02 does not alter the seven strategy-family formulas or Champion/Challenger decision authority.

It adds a dedicated training export because the v1.01 operational telemetry did not contain all exact 32 ONNX input values.

New inputs:

- `InpWriteTrainingData = true`
- `InpTrainingFile = "ComplexPolicy_ONNX_Training.csv"`

The training file is written to MT5 Common Files and contains exactly one row per signal bar with:

- `CP32_V1` feature contract id
- signal and decision-bar times
- closed-bar OHLC
- ATR
- first-tick decision bid/ask and spread
- SL/TP/max-hold policy metadata
- consensus
- all 32 exact ONNX feature values in contract order

The purpose is to build labels from future market outcomes, not from the existing strategy decision. This prevents the ML layer from merely learning to imitate the fixed rule engine.
