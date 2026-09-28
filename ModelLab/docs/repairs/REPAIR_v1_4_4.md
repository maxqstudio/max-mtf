# Repair v1.4.4 — Full KPI UI Authority / Hidden Hard-Gate Transparency

## Defect

`Advanced -> KPI & Evaluation -> KPI by Gate` exposed only a subset of the thresholds that the deterministic evaluators actually used for PASS/FAIL. A candidate could therefore fail a real backend hard gate whose threshold was not visible to the Owner.

Examples of previously hidden but active authority included Discovery median/worst Recovery Factor, positive month/quarter ratios, regime concentration, top-10% win concentration, spread-stress expectancy floors and threshold-plateau robustness; CPCV median/worst Recovery Factor; Tournament every-year nonnegative expectancy, regime concentration, top-10% win concentration and spread x1.50 expectancy. Enabled advanced risk metrics also had fail-closed evidence-sufficiency requirements that were described but not editable.

## Repair

- Preserve the existing `gate_kpis.<stage>` backend profiles and all evaluator formulas.
- Expose every active configurable hard PASS/FAIL threshold in `Advanced -> KPI by Gate`.
- Discovery now exposes the previously hidden survival, time/regime, concentration and execution-stress thresholds.
- CPCV now exposes median and worst Recovery Factor in addition to its existing economic/DD/path/PBO controls.
- Tournament now exposes `Every year Exp R >= 0`, maximum regime concentration, maximum top-10% winning-profit share and spread x1.50 expectancy floor.
- Risk-adjusted KPI sections retain ON/OFF and threshold controls and add an explicit `Risk KPI evidence sufficiency` disclosure for `min_trades`, `min_active_days`, `min_tail_days` and `min_sample_years` whenever those requirements exist.
- Monte Carlo already exposed its active hard-gate fields and is unchanged.
- Fresh Forward continues to expose every active economic/risk hard gate. Inactive degradation placeholders remain explicitly disclosed as inactive and are not presented as active KPI.
- Champion Promotion integrity requirements remain visible/read-only because they are governance invariants rather than tunable statistical KPI.
- Add `KPI_UI_HARD_GATE_CONTRACT` as a canonical visibility metadata registry so regression acceptance can detect future hidden configurable hard gates.
- Pending v1.4.2 advisor popover polish is included: compact model-size tooltip/popover content is centered. This changes presentation only.

## Engine boundary

The statistical evaluation engine is intentionally unchanged. `ModelLab/research/kpi.py`, `ModelLab/research/cpcv.py`, `ModelLab/factory/champion_factory.py`, `ModelLab/research/risk_kpi.py`, and `ModelLab/research/sample_policy.py` are byte-identical to v1.4.3. The repair changes the operator control surface and adds a visibility metadata/coverage guard only.

A new Factory is still required for changed KPI settings because gate profiles are frozen at START. An active/frozen run is never retroactively changed by editing Advanced settings.

## Regression

`R58_V144_KPI_UI_FULL_AUTHORITY` verifies:

- evaluation formula modules are byte-identical to v1.4.3;
- every field in the canonical active-hard-gate visibility contract has an operator-visible UI binding;
- every previously hidden KPI listed above is present;
- risk KPI evidence-sufficiency requirements are visible/editable;
- inactive Fresh degradation placeholders are not misrepresented as active KPI.

Cumulative local source/contract target: **135/135 exact-tree PASS**.
