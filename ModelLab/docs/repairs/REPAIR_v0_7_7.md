# Repair v0.7.7 — Optimizer Runtime + UI Authority

## Scope

Bounded repair over v0.7.6. No Research statistical formulas are changed.

## Closed defects

1. MetaEditor zero-error compile could be marked FAILED when CLI return code was non-zero. Compile authority is now explicit compiler summary + EX5; process return code is diagnostic only.
2. Strategy Optimizer previously deployed the packaged EA into MT5. v0.7.7 selects an existing Owner `.mq5` under `MQL5/Experts` and compiles it in place; evidence copy only.
3. Research and Strategy Optimizer footer CTAs could be cross-wired after page navigation because the left footer fragment stayed stale. Both authorities now remain mounted and workspace routing controls visibility.
4. Optimizer START no longer uses a second-click pending state; job creation occurs on the first click and heavy work remains in the background worker.
5. Strategy Optimizer now exposes editable/frozen Optimizer KPI and a live Scientist Optimizer Report.
6. Advanced information architecture is regrouped to reduce fragmentation. KPI by Gate uses one visual separator per gate; CPCV PBO is visible; PSR benchmark stays in the PSR row.

## Scientific boundaries retained

- Optimizer remains upstream of Research.
- Research H1 AUTO sample baseline remains 8 trades/month.
- Optimizer H1 default remains 20 trades/month and is independently configurable.
- PBO remains CPCV-only and NOT_COMPUTABLE until canonical cross-strategy input exists.
- Champion remains promotion/integrity/runtime authority rather than a sixth statistical gate.
