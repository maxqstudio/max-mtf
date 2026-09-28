# MAX Research Agent v1.2.4 — Strategy/Model Authority Page Separation + Owner E2E Audit

## Version authority
The release line is normalized to **v1.2.4**. The previous v0.12.3 package is historical; current authority is v1.2.4.

## UI authority separation
Model and Strategy promotion authorities are no longer rendered on combined pages.

Research/model pages:
- `Model Challengers` — ONNX/model Challenger registry, Shadow publish, model promotion.
- `Model Champion` — current production Model Champion plus Factory winner lineage/evidence.

Strategy pages follow the upstream tool explicitly:
- `Strategy Optimizer`
- `Strategy Challengers` — EA Challenger setup/KPI, promote/delete.
- `Strategy Champion` — current `Max.mq5`/`Max.set` strategy authority.

No Strategy Challenger or Strategy Champion controls are rendered on the Model pages.

## Owner Windows Golden E2E audit
The uploaded v0.12.3 Golden E2E evidence proves the synthetic sandbox lane reached WFA, all 15 CPCV splits, Tournament, Monte Carlo, Fresh Forward, ONNX export/runtime parity, human-readable Challenger registration, promotion precheck, sandbox promotion, and sandbox Champion deployment. Forward KPI propagation to Challenger evidence is 1:1 and all ONNX lineage copies are byte-identical.

One state-consistency defect was found: after successful promotion, `champion_registry.current` contained the new Champion while `supervisor_state.json.current_champion` remained null. v1.2.4 writes the promoted Champion entry into terminal supervisor state. `promotion_ready=false` remains correct after promotion because the same Challenger must not be promoted twice.

The legacy Factory core still uses internal terminal token `CHAMPION`. E2E evidence now adds `factory_lifecycle_status=ELIGIBLE_CHALLENGER` so Research output is not confused with production Model Champion authority. Production Model Champion still requires explicit promotion.
