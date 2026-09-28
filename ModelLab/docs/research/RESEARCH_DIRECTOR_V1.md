# CPMF Research Director V1 — v0.7.3 R5 workflow authority

## Purpose

The LLM Research Director remains Factory-level advisory intelligence. It cannot change KPI, chronology, model-registry bounds, open sealed downstream holdouts, or promote a Champion.

## Lifecycle

`START RESEARCH → Factory pre-flight → directed Generation 1 → WFA/OOF → Guided Research when needed → Generation review → directive for next generation → ... → frozen WFA Pool 12 → CPCV Finalists`

The pre-flight runs before Generation 1. Each generation review receives legal Discovery-side WFA/OOF, Guided Research and Research Memory evidence only. **v0.7.3 explicitly removes CPCV from the per-generation Director feedback loop.**

CPCV opens only after the WFA pool is frozen. Tournament, Monte Carlo, Fresh Forward, locked holdout and live evidence remain outside active Director research context.

## Two LLM scopes, one authority chain

- Factory Research Director: pre-flight and between-generation direction.
- Round Scientist: intra-generation review.
- Deterministic Supervisor/Research Kernel: sole executor and gate authority.

The Director and Scientist do not create an alternate evaluator or bypass `TemporalIndexContract`.

## Persistence and lifecycle

Factory reports remain in `historical external: research_director_journal.json`; per-generation Scientist reports remain in each run's `historical external: scientist_journal.json`. Global START/PAUSE/STOP/RESUME uses the existing `factory_jobs` worker lifecycle authority.

## R5 prior-cycle feedback boundary

The Director may see exact-contract Scientist summaries/hypotheses from a previously closed cycle. It may not see raw CPCV/Tournament/Monte-Carlo/Forward rows as Discovery tuning data. Stage-Scientist provenance survives Research Memory rehydration so the failure thesis can take priority over routine generation hypotheses.
