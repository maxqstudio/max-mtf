# Public Source Safety

This repository contains source code, governed specifications, documentation, and source-level tests only.

Excluded from Git history:
- Owner-PC runtime evidence and broker/runtime provenance
- market-data exports and imported native timeframe data
- acceptance screenshots, ZIP packages, logs, and local test artifacts
- compiled MetaTrader artifacts
- ONNX/model binaries and training artifacts
- machine calibration files
- credentials, environment files, private keys, tokens, and secrets

GitHub Actions is the source/development test authority. MetaTrader 5 / MetaEditor runtime acceptance remains an Owner-side final phase gate.

Do not commit private runtime evidence. CI evidence should remain ephemeral GitHub Actions artifacts.
