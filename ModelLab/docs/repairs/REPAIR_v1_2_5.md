# MAX Research Agent v1.2.5 — Strategy Champion Verified KPI Evidence

## Scope

This release imports the Owner-provided optimizer evidence for the existing Strategy Champion without changing trading logic or Champion parameters. It also includes the latest UI-only Strategy sidebar separator correction.

## Evidence join

The current 16-parameter Champion vector uniquely matches one row in `historical external: Max.xml` and one row in `Max_metrics.csv`. XML display Pass and MT5 frame pass ID are deliberately kept separate; the exact parameter vector is the join authority.

## Verified KPI

- PF: 1.024104
- RF: 0.472256
- Mean R: 0.0099404657441086
- Weighted R: 0.008513275799847675
- Profit: 799.94
- Trades: 1757
- Equity DD: 13.6676%
- Sharpe: 0.186698
- Expected Payoff: 0.455287
- R-accounted trades: 1757 / 1757
- Accounting errors: 0
- Initial risk sum: 93963.83000000006

Weighted R is independently verified as `sum_net / sum_initial_risk`.

## Authority

The compact evidence record is `historical external: ModelLab/evidence/research/OWNER_STRATEGY_CHAMPION_KPI_EVIDENCE.json`. Raw Owner files are not repackaged; their SHA-256 hashes are recorded in the evidence.
