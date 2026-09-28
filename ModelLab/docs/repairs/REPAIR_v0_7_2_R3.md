# CPMF v0.7.2 R3 — Research Director + Global Lifecycle Consolidation

## Trigger

Owner runtime showed two problems after Research Kernel V2 consolidation:

1. Global STOP/PAUSE controls were not visible as requested; controls were conditional inside the job monitor.
2. The LLM report appeared to stop. Source audit found the Round Scientist was intentionally skipped after the final Supervisor round because it was guarded by `experiments < max_exp`, and there was no Factory-level LLM pre-flight or generation review authority.

The screenshot showing `RESUME FROM LAST CHECKPOINT` also proves the specific captured worker was `INTERRUPTED`; no LLM can advance while the worker is not alive.

## R3 changes

- Adds Factory-level **Research Director V1**.
- Pre-flight LLM analysis is executed before Generation 1 candidate planning.
- Pre-flight strategy/hypotheses are consumed by the existing deterministic Supervisor initial planner; baseline remains fallback/control only.
- Adds a Director review after each committed Discovery generation using only WFA/OOF, CPCV, Guided and legal Research Memory evidence.
- Director directive is persisted and passed into the next generation.
- Round Scientist now reports after **every completed round, including the final round** when remaining experiment budget is zero.
- Factory generation identity is propagated through progress events and report display.
- Report de-duplication now includes Factory/generation/source identity; repeated round numbers across generations no longer collapse incorrectly.
- Event history window expanded for live report recovery; factory-level Director journal is persistent.
- Adds one always-visible global research lifecycle panel backed by existing `factory_jobs`: START / PAUSE / STOP / RESUME / FORCE STOP or ABORT according to state.
- All lifecycle button events are excluded from persisted Streamlit widget state.

## Unchanged scientific authority

R3 does **not** add Transformer, TCN, new fusion models, new KPI, new CPCV semantics, or cloud execution. Research Kernel V2 and `TemporalIndexContract` remain the evaluator authority introduced in R1. R2 event-state scrub remains active.

Tournament / Monte Carlo / Fresh Forward remain sealed from active Discovery learning and from the Research Director context.
