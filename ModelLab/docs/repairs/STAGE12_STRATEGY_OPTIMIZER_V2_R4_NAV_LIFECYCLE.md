# Stage 12 Strategy Optimizer V2 R4 - Navigation & Lifecycle Separation

Status: LOCAL REPAIR CANDIDATE. Owner MT5 runtime remains external.

## Owner contract

Strategy Optimizer is not part of `Start Auto Research`. It is a separate pre-model tool with its own worker, state, evidence, stop action and runtime acceptance.

Sidebar order is locked to:

1. Research
2. Data
3. Discovery
4. Pool
5. CPCV
6. Tournament
7. Monte Carlo
8. Forward Championship
9. Champion
10. Advanced
11. separator
12. Strategy Optimizer

`Strategy Optimizer` must remain the final navigation item below a visible separator so it cannot be read as another ModelLab validation stage.

## Contextual footer authority

The fixed left footer is contextual without sharing handlers:

- Any normal ModelLab page -> `START AUTO RESEARCH` / existing Research lifecycle.
- `Strategy Optimizer` page -> `START AUTO OPTIMIZER` / Strategy Optimizer lifecycle.
- Active optimizer -> `STOP OPTIMIZER`.

The Optimizer footer must call only `strategy_optimizer_jobs.start_job/cancel_job`. It must never call Factory AUTO/MANUAL/Discovery start handlers.

The Research footer must never call Strategy Optimizer start/cancel handlers. Research and Optimizer starts are mutually blocked while the other lifecycle is active to avoid ambiguous ownership and resource contention.

The Strategy Optimizer page itself is configuration + evidence/status only. It must not carry a second duplicate START/STOP row.

## Status authority

On Strategy Optimizer page, the app bar reports Optimizer state (`OPTIMIZER IDLE`, active MT5 state/round, or terminal result). It must not report Research `IDLE` while an optimizer job is active.

## Existing R3 runtime diagnostics preserved

R4 preserves R3 automatic diagnostics:

- no manual EA copy;
- automatic packaged-EA deployment and MetaEditor compile;
- automatic evidence folder under `owner_acceptance/evidence/strategy_optimizer/<job_id>/`;
- automatic compile/error excerpt in UI;
- downloadable diagnostic ZIP;
- `Relative reference symbol` wording for Strategy 7 Relative Value;
- optimizer KPI: PF >= 1.00, RF >= 0.00, Expectancy R >= 0.00, closed trades > 0.

No ModelLab scientific KPI or validation contract changes in this repair.
