# Repair v0.8.8 — Strategy Optimizer Frame Identity

## Defect

A real MT5 Fast Genetic run produced opaque 64-bit optimization frame pass IDs such as `5790963814160864255`. v0.8.7 parsed the CSV `pass` field through Python `float` before converting to `int`. Values above `2^53` are not exactly representable in IEEE-754, so distinct frame IDs collapsed to the same integer and the worker failed with `Duplicate optimizer R-metrics pass`.

The same Owner evidence also proved that the frame-pass namespace is not the SpreadsheetML display `Pass` namespace (`Max_metrics.csv` contained opaque uint64 IDs while `historical external: Max.xml` contained contiguous display pass numbers). Therefore joining Weighted-R sidecar evidence to XML by pass number was scientifically invalid even after removing the float precision bug.

## Repair

- `Max.mq5` now preserves `FrameNext.pass` as unsigned text using `%I64u`; it is never cast through `long` or `double`.
- `Max.mq5` calls the official MT5 `FrameInputs(pass, ...)` API for every `MAX_R_METRICS` frame and serializes the exact input vector into `Max_metrics.csv`.
- Python treats the frame pass ID as provenance only.
- Python joins sidecar Mean-R/Weighted-R evidence to the XML row by the canonical 16-parameter Strategy Optimizer input vector.
- Join validation additionally requires Mean R, MT5 trade count, and net profit parity between XML and frame evidence.
- Duplicate exact frame IDs, duplicate parameter vectors, missing/extra parameter vectors, nonce mismatch, accounting mismatch, and arithmetic mismatch all fail closed.
- Legacy v0.8.5-v0.8.7 sidecars without `frame_inputs` are intentionally rejected for new v0.8.8 production parsing.

## Regression

`ModelLab/tests/v088_optimizer_frame_identity_selftest.py` uses two adjacent 64-bit frame IDs that collapse to the same Python float and reverses XML/sidecar row order. PASS requires both IDs to remain distinct and Weighted R to attach to the correct XML pass solely through `FrameInputs` parameter identity.

## Runtime gate

Local Python/source acceptance cannot replace MetaEditor + real MT5 proof. Owner runtime must compile v0.8.8 and perform a fresh optimization producing the v0.8.8 `Max_metrics.csv` schema.
