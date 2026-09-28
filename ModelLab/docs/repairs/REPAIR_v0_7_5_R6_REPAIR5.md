# Max Research Agent — ONNX Factory v0.7.5 R6 Repair5

## Quote-gate correction

Owner runtime audit on the verified Monex-Demo EURUSD.m H1 dataset exposed `INVALID_DECISION_QUOTE_ROWS:385` while broker timestamp/OHLC reconciliation was 100%, duplicates were zero, and no source-backed bars were missing.

R4 incorrectly classified `decision_ask == decision_bid` as structural corruption. A zero-spread broker observation is unusual and must remain visible, but it is not equivalent to a non-finite, non-positive, or inverted quote. The hard data gate therefore over-blocked a dataset that can be label-evaluated with zero transaction spread on those rows.

Repair5 changes the deterministic authority as follows:

- `ask == bid`, with finite positive bid/ask, is `ZERO_SPREAD_DECISION_QUOTE_ROWS` and is a warning.
- non-finite bid/ask remains hard FAIL.
- non-positive bid/ask remains hard FAIL.
- inverted `ask < bid` remains hard FAIL.
- label construction now uses the same authority and accepts a finite positive zero-spread observation.
- Data Quality UI reports `Quote invalid` and `Zero-spread` separately.
- cached R4 audit results are schema-invalidated automatically after this upgrade.

No interpolation, synthetic quote, missing-bar weakening, broker-reconciliation weakening, KPI weakening, or research-authority bypass was introduced.
