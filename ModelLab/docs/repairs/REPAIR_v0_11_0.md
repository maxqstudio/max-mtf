# Repair v0.11.0 — Strategy Challenger / Champion Lifecycle

v0.11.0 makes the upstream Strategy Optimizer follow the same explicit Challenger → Champion authority split already used by Model Research.

## Strategy Optimizer output

An eligible MT5 optimizer winner no longer mutates the canonical Strategy Champion automatically. The optimizer stops at `STRATEGY_CHALLENGER_FOUND` and creates an immutable human-readable Strategy Challenger bundle:

- `EA_v1_06/strategy_challengers/Max_Challenger_STRAT-<UTC>-R<round>-P<pass>.mq5`
- matching `.set` with every optimizer-owned parameter fixed and optimization disabled
- matching `.json` metadata with exact setup, KPI, hard gates, provenance and SHA-256 integrity

The current `EA_v1_06/Max.mq5`, canonical Tester `Max.set`, and Python `ModelLab/runtime/strategy_authority.json` remain unchanged while a Challenger is merely registered.

## Strategy KPI registry

The Strategy Optimizer UI shows one current Strategy Champion and all active Strategy Challengers. Each optimizer-created Challenger carries:

- Profit Factor
- Recovery Factor
- Mean R
- Weighted R
- net Profit
- closed Trades
- complete optimizer-owned parameter setup
- frozen optimizer hard gates and source round/pass provenance

For the imported v0.10.0 Strategy Champion, KPI evidence is recovered automatically when a matching historical optimizer run is available. If only the imported EA parameter authority exists, KPI fields remain explicitly unavailable; values are never fabricated.

## Explicit promotion

`PROMOTE TO STRATEGY CHAMPION` is the only promotion authority.

Promotion is transactional:

1. verify selected Challenger EA/set hashes and parameter bundle;
2. snapshot the current Champion;
3. save the current Champion as a new uniquely coded Strategy Challenger;
4. apply selected Challenger parameters to canonical `Max.mq5`;
5. write canonical Tester `Max.set` at the exact promoted fixed point;
6. verify EA ↔ Max.set parity;
7. compile/deploy canonical Max through MetaEditor;
8. persist Python Strategy execution authority / geometry;
9. commit the registry transition.

Any failure restores the previous `Max.mq5`, canonical Tester `Max.set`, runtime Strategy authority, and registry state.

## Former Champion demotion

A successful promotion never destroys the previous Strategy Champion. The old Champion becomes a normal active Challenger with a new human-readable code and preserves its setup plus all available KPI evidence.

## Delete authority

Only active Strategy Challengers may be deleted. The current Strategy Champion cannot be deleted. Challenger `.mq5`, `.set`, and metadata files are removed, while a compact tombstone preserves identity, setup/KPI provenance and deletion time for scientific audit.

## Research boundary

Model Research continues consuming only the **current promoted Strategy Champion** execution geometry. Merely creating a Strategy Challenger does not change CP32/model authority. After Strategy promotion, stale CP32 data must fail closed until training data is regenerated with the newly promoted `Max.mq5`.

## Unchanged contracts

v0.11.0 does not change strategy signals, ATR SL/TP behavior, risk-cap sizing, R accounting, MT5 Result = Mean R, Weighted R arithmetic, model decision shape `[N,3]`, or Model Challenger lifecycle.
