# KPI Acceptance V3 — SURVIVAL_STRICT_V1

## Authority hierarchy

`selection_score` ranks research candidates only. It cannot compensate for a failed acceptance gate. Authority is:

1. Walk-forward current-policy gate.
2. Locked-test KPI_V3 gate.
3. ONNX parity.
4. MT5 parity.
5. Strategy Tester integration.
6. Fresh shadow KPI gate.
7. Same-window Champion-relative gate.
8. Explicit promotion authority.

## Default strict policy

### Walk-forward
- validation trades >= 150
- median PF >= 1.30
- median expectancy >= 0.25R
- worst-fold expectancy >= 0.00R
- positive-fold ratio >= 0.66
- median recovery >= 1.50

### Locked test
- trades >= 100
- PF >= 1.50
- expectancy >= 0.50R
- max DD <= 15R
- recovery >= 3.00
- positive months >= 50%
- positive quarters >= 50%
- dominant positive-regime contribution <= 85%
- top 10% winning trades contribution <= 55% of gross winning R
- ONNX native parity max abs error <= 1e-4

### Stress
- spread x1.25 expectancy >= 0.20R
- spread x1.50 expectancy >= 0.10R
- take-threshold profitable plateau >= 75%

### Fresh shadow before promotion
- trades >= 100
- PF >= 1.50
- expectancy >= 0.50R
- max DD <= 15R
- recovery >= 3.00

## Promotion revalidation

Governance never trusts only the historical `ELIGIBLE_CHALLENGER` label. On every promotion assessment it recalculates walk-forward and locked-test acceptance from saved evidence against the **currently active policy**. If the operator raises a threshold after a run, that candidate must satisfy the new threshold or promotion fails closed.

Machine-readable evidence: `historical external: promotion_kpi_assessment.json`. Champion archive stores the promotion KPI assessment and policy snapshot.
