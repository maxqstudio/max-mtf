# Max Research Agent — ONNX Factory v0.7.5 R6 Repair4

## Scope

Repair4 adds a deterministic **Data Quality Authority + broker-backed gap-repair gate** and hardens LLM availability routing. It is built on the latest accepted Max UI from Repair3; Advanced layout, big-card disclosure hierarchy, Max branding, hybrid-family display parser, and proportional CONNECT action are preserved.

## Data Quality Authority

`START RESEARCH` no longer treats duplicate-free CP32 as sufficient evidence that the dataset is research-ready.

The deterministic audit checks:

- CP32 required columns and feature contract;
- unique symbol/timeframe and duplicate identity rows;
- parseable chronology;
- OHLC / ATR / decision-quote sanity;
- finite and non-degenerate CP32 feature health;
- observed timestamp discontinuities for diagnostics only;
- reconciliation against the **same active MT5 broker feed**.

### Broker/feed reconciliation

Max does **not** construct a naive 24/7 H1 calendar. Weekend, holiday and broker-session closures therefore cannot be mislabeled as missing merely because wall-clock timestamps jump.

The MT5 reference must first be verified by:

1. high timestamp overlap after deterministic broker/server-time offset inference; and
2. high OHLC agreement against the broker bars using the symbol point as price tolerance.

Only after both checks pass may a broker timestamp absent from the CSV be called a `source-backed missing bar`.

Research readiness is fail-closed if:

- broker reconciliation is not verified;
- source-backed bars are missing;
- dataset-only timestamps exist;
- structural/schema/market sanity gates fail.

## Gap repair authority

Missing bars are never synthesized or interpolated.

The repair path is:

`verified MT5 broker history -> existing ComplexPolicy_ONNXReady_EA Strategy Tester -> CP32 first-write-wins writer -> re-audit`

The existing EA remains the CP32 feature-generation authority. Existing rows are preserved and only absent identity timestamps are appended. The repair launcher is restricted to the exact MT5 installation/data directory that produced the verified broker reconciliation; another installed terminal cannot be selected accidentally.

The Owner-machine MT5 gap-fill execution itself is an external runtime gate and is not claimed PASS in this build environment.

## LLM Data Review before Research Director pre-flight

After deterministic Data Quality PASS and LLM route preflight, the committed `DATA` Scientist stage receives a bounded, row-free `data_quality_profile` before the Factory Research Director creates the Generation-1 research thesis.

The LLM receives only summary evidence such as dataset identity, structural/market health, feature warnings, broker verification, timestamp/OHLC match ratios, and missing-bar counts. Raw CSV rows are not sent.

Deterministic data gates remain authority. LLM interpretation is advisory only.

## LLM availability contract

At `START RESEARCH`, Max executes an actual lightweight ordered-stack route probe.

Retryable conditions traverse the configured stack in order:

- quota / daily quota exhausted;
- rate limit;
- timeout;
- model unavailable / provider capacity;
- provider 5xx;
- health cooldown.

The same ordered fallback applies to Scientist/Director calls during research. When every configured route is retryably exhausted, Max explicitly enters deterministic research mode and continues instead of aborting the Factory.

Non-retryable defects remain fail-closed:

- invalid authentication/API key;
- invalid endpoint/config/request;
- malformed deterministic/LLM schema or validation failure.

Every attempt and selected route remains in LLM provenance.

## UI continuity

Repair4 intentionally preserves the latest Owner-approved UI baseline:

- `Max Research Agent · ONNX Factory` branding;
- accepted Advanced disclosure structure;
- first-level big-card hide/show only;
- no nested show/hide for inner groups;
- `hybrid::gru::xgboost` is display-formatted as `GRU → XGBoost` while canonical backend IDs remain unchanged;
- CONNECT action remains proportionally aligned.

The only new major UI grouping is `Data quality · MT5 broker reconciliation` on the dataset/research setup surface.

## New acceptance gates

- `R15_DATA_QUALITY_BROKER_GAP_AUTHORITY`
- `R15_LLM_AVAILABILITY_DETERMINISTIC_FALLBACK`

All previous cumulative gates must still PASS before sealing Repair4.

## Build acceptance

`73 / 73 PASS` · `first_failed_gate = null` on the exact Repair4 source before package sealing.
