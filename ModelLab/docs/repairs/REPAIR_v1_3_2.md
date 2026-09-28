# REPAIR v1.3.2 — Scientific Workflow Production-Parity Repair

## Scope

v1.3.2 closes the scientific defects recorded in `ModelLab/docs/research/SCIENTIFIC_WORKFLOW_AUDIT_v1_3_1.md` without changing the promoted Strategy Champion EA parameter vector.

## Execution parity

- **SCI-01 CLOSED** — Model Research loads the promoted Strategy Champion execution policy as runtime authority. Entry threshold, reverse-exit threshold, minimum consensus, shock halt, spread limit, blend, SL, TP and MaxHold are synchronized fail-closed at START.
- **SCI-02 CLOSED** — WFA/CPCV/Tournament/Fresh policy returns use `MAX_STATEFUL_EXECUTION_SIM_V1`: one active position, broker-side SL/TP exposure, MaxHold and no overlapping entries.
- **SCI-03 CLOSED** — Research replay implements Champion `REVERSE_EXIT` and permits same-decision re-entry only when the canonical entry gates admit it, matching EA ordering.
- Spread stress widens quote/spread inputs used by the stateful replay; it no longer mutates obsolete counterfactual `long_r/short_r` columns only.

## Labels and training

- **SCI-04 CLOSED/MITIGATED BY CONTRACT** — Output remains `[P(SELL), P(SKIP), P(BUY)]`, but supervised rows receive bounded R-utility weights. Reverse exit is endogenous to model scores and therefore remains execution-evaluation authority rather than being fabricated into ex-ante labels.
- **SCI-05 CLOSED** — Structurally non-executable rows remain temporal context but have `supervised_weight=0`; they cannot consume actionable supervised-loss authority.
- **SCI-06 CLOSED** — immutable `source_row_id` survives labeling. Ambiguous/unavailable rows are retained as context instead of being physically removed, so temporal sequence builders cannot silently bridge deleted chronology.
- Tree, temporal, hybrid, CPCV, Full-WFA, refit and Forward training paths all consume the supervised-weight contract.

## KPI/scoring

- **KPI-01 CLOSED** — Daily CVaR is explicitly a signed lower-tail return floor. Positive thresholds fail closed unless `allow_positive_tail_floor=true`; normal UI range prevents accidental positive loss floors.
- **KPI-02 CLOSED** — candidate selection uses `CV_SCORE_V5_FIXED_100`. Fixed score weights total exactly 100 and do not change when Owner hard KPI toggles are enabled/disabled. Hard PASS/FAIL remains separate from ranking score.
- **KPI-03 CLOSED** — Sharpe/Sortino/Calmar/PSR/DSR/Ulcer/CVaR are sample-aware. Insufficient trades/days/tail-days/sample-years fail as explicit `*_EVIDENCE` / `sample_sufficiency`, not falsely as poor model quality.
- **KPI-04 CLOSED** — Cheap Screen treats advanced risk KPI as diagnostic-only. Full WFA remains the first hard risk-adjusted qualification authority.
- **KPI-05 CLOSED** — Fresh Forward carries the production economic bar: PF >= 1.50, Mean R >= +0.50R, RF >= 3.00, Max DD <= 10R, plus its stage-specific risk profile. Promotion adds no hidden second market test.

## CPCV / WFA / feature audit

- **CPCV-01 CLOSED AS OPTIONAL COMPUTABLE AUTHORITY** — cross-strategy six-group CPCV OOS expectancy matrix supports CSCV-style PBO. PBO is OFF by default, requires at least four finalists, and fails closed for insufficient matrix evidence when Owner enables it. Candidate-local pseudo-PBO remains forbidden.
- **WFA-01 CLOSED** — configured `split.min_train_rows` is honored; small selftests must opt into smaller fixture-specific values explicitly.
- **FEAT-01 CLOSED AS REQUIRED ABLATION** — `RULE_META_SCORE` double-exposure is not silently removed; Guided Research exposes a bounded `ABLATION · RULE_META_SCORE` experiment so evidence determines whether rule-meta-as-feature plus post-model blend is beneficial.

## Default hard-risk hierarchy

- Discovery: Sharpe >= 0.15, Sortino >= 0.25, Ulcer <= 8R. Other advanced metrics diagnostic.
- CPCV: Sharpe >= 0.20, Sortino >= 0.30, Ulcer <= 8R, daily CVaR >= -2.5R. Optional PBO <= 0.20 when enabled.
- Tournament: Sharpe >= 0.30, Sortino >= 0.50, Calmar >= 1.00, PSR >= 0.80, Ulcer <= 6R, daily CVaR >= -2.0R. DSR diagnostic by default.
- Fresh: Sharpe >= 0.40, Sortino >= 0.65, Calmar >= 1.25, PSR >= 0.85, Ulcer <= 5R, daily CVaR >= -1.5R. DSR diagnostic by default.

## Regression authority

`ModelLab/tests/v132_scientific_workflow_repair_selftest.py` verifies execution-policy synchronization, stateful/reverse-exit replay, label masking/chronology, fixed-100 scoring, CVaR sign safety, sample sufficiency, Cheap Screen risk isolation, Fresh production bar, PBO computation and rule-meta ablation.

The cumulative v1.3.2 acceptance gate is `R51_V132_SCIENTIFIC_WORKFLOW_REPAIR`.

## Fresh-readiness label-maturity follow-up

- `build_labels()` now intentionally retains immature horizon-tail rows as chronology/context with `label_valid=false` and zero supervised authority.
- `fresh_readiness()` therefore filters on `label_valid` before counting `labeled_fresh_rows`; context-only SKIP placeholders can no longer make a not-yet-mature Fresh window report `READY`.
- `ModelLab/tests/data_integrity_selftest.py` covers both READY-after-maturity and `WAITING_LABEL_HORIZON` before maturity under the complete v1.3.2 Strategy execution authority.
