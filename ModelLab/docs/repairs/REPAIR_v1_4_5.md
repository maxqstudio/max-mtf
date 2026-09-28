# Repair v1.4.5 — Model Detail Inspector / Live Runtime Observability

## Defects

Two UI/runtime observability gaps remained after v1.4.4:

1. Candidate/model tables exposed KPI outcomes but not the exact frozen model setup or a trustworthy model-size view. The Owner could not inspect one listed candidate without leaving the stage and manually tracing artifacts.
2. Research and Strategy Optimizer lifecycle/loading status could become visually stale until a browser refresh, and the sidebar activity indicator still rendered as a card-like block instead of a flat lifecycle status surface.

## Repair

### Reusable Model Detail Inspector

- Add a read-only `MAX_MODEL_DETAIL_INSPECTOR_V1` resolver over committed Factory/Run artifacts.
- A single selected row now opens the same inspector across Research live candidates, Discovery near-miss, Pool, CPCV, Tournament, Monte Carlo, Forward Championship, Model Challengers, current Model Champion, and Factory winner evidence.
- Neural/temporal families show executable trainable parameter count when it is available from committed evidence or can be deterministically derived from the frozen executable architecture.
- Dynamic temporal->tree hybrids show the temporal-leg trainable parameter count plus the policy-tree complexity.
- Tree families never receive a fabricated neural-style parameter count. The inspector shows the frozen tree setup and, when deterministic from hyperparameters, a clearly labelled structural node upper bound; exact fitted node count remains data-dependent.
- Exact stored candidate parameters win. Historical evidence with no exact parameter payload stays explicit as unavailable; the UI does not reconstruct or guess values.
- Inspector code is read-only and has no mutation authority over candidate, Factory, promotion, or lifecycle state.

### Live Research / Optimizer status

- Research Factory live monitor is a 2-second fragment that re-reads committed job evidence automatically.
- Contextual left-footer Research/Optimizer lifecycle remains a 2-second fragment and now renders loading/activity as a flat status strip rather than a card-like busy block.
- Strategy Optimizer main runtime status remains a 2-second fragment.
- Research and Optimizer lifecycle wrappers are explicitly borderless/transparent in the left footer.
- Polling is read-only; START/PAUSE/STOP/RESUME and Optimizer lifecycle actions remain the existing process-authoritative handlers.

## Scientific boundary

This repair does **not** change Research search, acceptance KPI, CPCV, Tournament, Monte Carlo, Forward, model training, Strategy Optimizer orchestration, or promotion logic. The following authority modules remain byte-identical to v1.4.4 and are locked by regression: `ModelLab/research/kpi.py`, `ModelLab/research/cpcv.py`, `ModelLab/factory/champion_factory.py`, `ModelLab/research/risk_kpi.py`, `ModelLab/research/sample_policy.py`, `ModelLab/models/models.py`, `ModelLab/factory/supervisor_agent.py`, `ModelLab/research/research_architect.py`, `ModelLab/models/model_registry.py`, `ModelLab/factory/factory_jobs.py`, and `ModelLab/strategy/strategy_optimizer_jobs.py`.

## Regression

`R59_V145_MODEL_INSPECTOR_LIVE_RUNTIME` verifies:

- exact frozen setup resolution and trainable-parameter count for neural candidates;
- no fabricated parameter count for tree families and deterministic structural upper-bound semantics;
- hybrid temporal-count + policy-tree complexity visibility;
- inspector read-only behavior;
- selectable inspector wiring across every current Research candidate/model list;
- 2-second Research Factory, contextual lifecycle, and Optimizer runtime polling;
- flat/borderless Research and Optimizer sidebar loading status;
- byte-identical scientific/runtime authority modules relative to v1.4.4.

Cumulative local source/contract target: **136/136 exact-tree PASS**.
