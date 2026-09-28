# CP_POLICY_V1 · Bounded OOF Policy Discovery

## Purpose

Policy Discovery is a second research stage used only when the model hyperparameter frontier fails walk-forward acceptance but still shows measurable predictive signal. It does not reopen, inspect, or optimize against the locked test.

Flow:

`MODEL_SEARCH -> OOF_POLICY_DISCOVERY -> (CV PASS -> LOCKED_TEST | CV FAIL -> FEATURE_LABEL_AUDIT)`

## Authority

The deterministic Supervisor owns this stage. The LLM Scientist may summarize evidence and suggest research direction, but cannot alter labels, splits, KPI thresholds, risk/execution controls, or locked-test authority.

## Search space

CP_POLICY_V1 may only make the model more selective using:

- take probability threshold
- separate BUY probability threshold
- separate SELL probability threshold
- directional probability margin
- maximum probability entropy
- bounded regime mode (`ALL`, `NON_SHOCK`, `TREND_RANGE`, `TREND`, `RANGE`)

The fixed deployment gates remain active: consensus, entry threshold, spread limit, shock halt, ONNX blend, and fixed execution/risk policy.

## KPI and acceptance

Every policy is scored with the same 28 walk-forward-observable KPI components used by model ranking. A policy cannot open the locked test unless the full walk-forward acceptance gate passes under the current `SURVIVAL_STRICT_V1` profile.

The locked test remains sealed throughout Policy Discovery. If no policy passes, the next required stage is `FEATURE_LABEL_AUDIT`, not an automatic increase in hyperparameter budget.

## Deployment contract

An accepted policy is exported as `challenger_policy.csv` next to `challenger.onnx`.

Schema: `CP_POLICY_V1`.

Promotion is fail-closed if a manifest requires CP_POLICY_V1 but the exact policy artifact is missing. Promotion archives and deploys the matching policy as `champion_policy.csv` together with `champion.onnx`.
