# v0.6.0 · Policy Discovery & Deployable Selectivity

## Why this release exists

The 36-experiment evidence showed model hyperparameter search improving selectivity but still failing economic walk-forward gates, while classification metrics remained above a random three-class baseline. v0.6.0 therefore adds a bounded decision-policy research stage instead of simply increasing model-search budget.

## Implemented

- deterministic OOF Policy Discovery after failed model CV when predictive signal is present
- CP_POLICY_V1 search over take/BUY/SELL/margin/entropy/regime selectivity
- same 28-KPI composite score and current walk-forward gate for every policy candidate
- locked test remains sealed until a model+policy pair is CV-eligible
- fail-forward research state `FEATURE_LABEL_AUDIT` when bounded policy search also fails
- `historical external: policy_discovery.json` and `historical external: policy_leaderboard.json` evidence
- accepted `challenger_policy.csv` deployment artifact
- policy-aware locked-test KPI calculation
- policy-aware Challenger shadow installation
- promotion gate requires exact policy artifact when the model manifest declares CP_POLICY_V1
- Champion archive/deployment copies `champion_policy.csv`
- EA v1.03 reads CP_POLICY_V1 and logs Challenger policy TAKE/SKIP decisions
- UI shows Policy Discovery live table and human-readable policy leaderboard
- optional LLM Scientist review after Policy Discovery

## Acceptance

`historical external: BUILD_ACCEPTANCE_v0_6_0.json` is machine-readable. The one-click `ModelLab/RUN_ACCEPTANCE.cmd` continues to execute `ModelLab/tests/acceptance_selftest.py`.

Local acceptance includes a real tiny XGBoost OOF Policy Discovery run, all-28-KPI scoring, policy artifact generation, fail-closed promotion without the policy file, current-policy promotion revalidation, and Champion-relative negative path.

MQL5 compilation and real Windows ONNX conversion remain external runtime gates and are not claimed by this package.
