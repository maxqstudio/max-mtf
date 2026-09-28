# KPI Acceptance V5 · Hierarchical Survival-First

## Authority rule

Composite Score is **ranking only**. It can never turn a failed candidate into PASS.

A candidate passes only when **every mandatory gate** at the active stage passes. Evaluation order is intentionally fail-closed:

1. Integrity / sufficient samples
2. **Survival**
   - Drawdown
   - Recovery Factor
3. Economic edge
   - Profit Factor
   - Expectancy
4. Cross-fold / time / regime robustness
5. Execution / spread / threshold stress
6. Classification metrics are diagnostic/ranking evidence only

## Priority

For ranking candidates that are in the same PASS/FAIL authority class:

- Drawdown combined weight: **22**
- Recovery combined weight: **12**
- Profit Factor weight: **8**

Therefore `DD > Recovery > PF`. PF remains mandatory and must stay high, but PF cannot compensate for unsafe drawdown or weak recovery.

## H1 default authority

### Walk-forward

- validation trades >= 90
- median Max DD <= 12R
- worst-fold Max DD <= 18R
- median Recovery >= 1.50
- worst-fold Recovery >= 1.00
- median PF >= 1.25
- median Expectancy >= +0.10R
- worst-fold Expectancy >= -0.03R
- positive folds >= 66%
- positive months >= 55%
- positive quarters >= 60%
- dominant positive regime concentration <= 75%
- top-10% winning-profit concentration <= 55%
- spread x1.25 Expectancy >= +0.08R
- spread x1.50 Expectancy >= +0.05R
- threshold plateau >= 66%

### Locked / fresh holdout

- trades >= 50
- Max DD <= 12R
- Recovery >= 2.00
- PF >= 1.35
- Expectancy >= +0.15R
- positive months >= 55%
- positive quarters >= 60%
- dominant positive regime concentration <= 75%
- top-10% winning-profit concentration <= 55%
- spread x1.25 Expectancy >= +0.08R
- spread x1.50 Expectancy >= +0.05R
- threshold plateau >= 66%
- ONNX parity remains a hard gate

## No compensation

Examples that must FAIL:

- PF 3.0 but Max DD 25R
- PF 2.0 but Recovery 0.6
- excellent median metrics but one fold breaches worst-fold survival gates
- strong trading metrics but spread stress collapses
- high Composite Score while any mandatory gate fails
