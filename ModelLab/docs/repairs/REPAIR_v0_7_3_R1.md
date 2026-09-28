# CPMF v0.7.3 R1 — Workflow Gate Reorder

## Scope

Workflow repair only. No trading KPI threshold, label authority, model family, GRU architecture, Tournament KPI, Monte Carlo KPI, Forward KPI, or Research Kernel V2 chronology semantics were changed.

## Defect repaired

v0.7.2 R4 ran CPCV inside every Discovery generation. A WFA candidate could consume full combinatorial CPCV compute before the Factory had assembled a frozen finalist pool. On CPU this made CPCV a repeated HPO bottleneck and prevented efficient exploration of the rest of the Champion Factory workflow.

## v0.7.3 R1 authority

`Discovery WFA/OOF → frozen Pool 12 → CPCV Finalists → Tournament → Monte Carlo → Forward Championship → Champion`

Discovery now adds a candidate to Pool only after existing WFA/OOF PASS. CPCV is deferred.

The separate CPCV stage:
- freezes finalist ranking from WFA/OOF evidence before CPCV opens;
- evaluates finalists progressively;
- default target = 3 CPCV survivors;
- default batch = 3;
- default maximum finalists = 12;
- stops early when survivor target is reached;
- opens Tournament only with `CPCV_SURVIVORS_READY`;
- fails closed as `CPCV_NO_SURVIVOR` when no finalist survives;
- does not feed CPCV outcomes into active per-generation Research Director/Research Memory.

## Resume

Discovery checkpoints use WFA-pool boundaries. CPCV persists a frozen finalist plan and candidate-level progress. If interrupted inside one candidate's CPCV paths, that unfinished candidate may be replayed; completed finalists are retained.

## Acceptance

36 local gates PASS. See `historical external: BUILD_ACCEPTANCE_v0_7_3_R1.json`. Owner Windows/MT5 external gates remain required.
