# v0.5 Adaptive Supervisor Repair

- Removed hardcoded `xgb_d3/xgb_d5/lgb_leaf15/lgb_leaf31/rf_d10/rf_d16` seed population.
- Added external `ModelLab/config/models/model_registry.json` for legal families and hyperparameter bounds.
- Added stratified discovery population.
- Added adaptive family weighting with minimum exploration floor.
- Added global exploration, local refinement, and same-family crossover.
- LLM Scientist can advise bounded exploration ratio and family priorities in addition to candidate proposals.
- Added `historical external: supervisor_plan.json` research lineage.
- Locked test, acceptance, ONNX, Challenger/Champion governance remain deterministic.
- Existing result table presentation is intentionally unchanged.
