# Stage 12 Strategy Optimizer V2 — Rebase Audit

**Accepted rebase source:** `MAX_RESEARCH_AGENT_ONNX_FACTORY_v0_7_5_R6_UI_SIDEBAR_CLEAN_R1_OWNER_RETEST.zip`

**Rejected source for Stage 12 delivery:** the earlier Stage 12 V2 package built from the older Stage 1–11 backend checkpoint/root layout. It is historical failed delivery evidence only.

## Rebase rule

Start from the exact UI Sidebar Clean R1 package and apply only the Strategy Optimizer V2 feature delta plus Stage 12 tests/docs/authority metadata. Do not import the old root layout, rejected Anti-Slop UI experiments, or unrelated runtime/UI source.

## Expected runtime delta

- `ModelLab/ui/app.py`: add one top-level `Strategy Optimizer` page and its imports/render route.
- `ModelLab/strategy/strategy_optimizer.py`: MT5 installation discovery, bounded search-space compiler, XML parser, inclusive optimizer KPI filter, deterministic selection/refinement, bounded Scientist proposal.
- `ModelLab/strategy/strategy_optimizer_jobs.py`: background job lifecycle.
- `ModelLab/strategy/strategy_optimizer_worker.py`: MetaEditor compile + native MT5 optimization rounds.
- `ModelLab/strategy/strategy_optimizer_runtime_acceptance.py`: Owner-machine evidence gate.
- `EA_v1_06/Max.mq5`: tester-only seven-family guard and realized R `OnTester()`.
- Stage 12 test/doc/acceptance files and navigation-aware acceptance fixture updates.

## Owner KPI lock

Strategy Optimizer eligibility only:
- PF `>= 1.00`
- RF `>= 0.00`
- Expectancy R `>= 0.00`
- closed trades `> 0`

These thresholds are deliberately not ModelLab production validation thresholds.

## Package-layout rule

Root remains the organized layout: only `README_FIRST.md` plus `ModelLab/`, `EA_v1_06/`, `governance/`, `owner_acceptance/`, `history/`, `migration_tools/`.
