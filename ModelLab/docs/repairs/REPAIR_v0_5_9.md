# v0.5.9 — Adaptive Operator UI, Scientist Report, Complete KPI Score

## Operator UI

- Removed fixed `1180px` content width. The control center now uses adaptive width up to `96vw / 1920px` with responsive padding.
- Removed operator-facing raw JSON rendering from KPI diagnostics and Scientist journal.
- Added a live **LLM Scientist report** panel beside research progress. The user does not need to type a chat prompt.
- Scientist reports are rendered as condition, interpretation, next action, confidence, family priorities, and proposed experiments.
- `historical external: scientist_journal.json` remains machine-readable backend evidence.

## KPI / ranking

- Added a complete KPI scorecard in Results.
- Replaced the old thin score with `CV_SCORE_V2_ALL_KPI`.
- All 28 CV-observable KPI components contribute to the ranking score with total weight 100.
- Locked-test-only evidence remains sealed and never contributes before CV acceptance.
- Added score category breakdown for auditability.
- Rich leaderboard now exposes the major KPI fields used by the score.

## Research defaults

For the current fast-research cycle:

- XGBoost: ON
- LightGBM: ON
- Random Forest: OFF by default, still available
- GRU: research lock unchanged until temporal sequence authority exists end-to-end

## Governance

Promotion authority from v0.5.8 remains intact. KPI score changes affect research ranking only; they do not bypass acceptance or promotion gates.
