# CPMF v0.7.2 R2 — Streamlit UI Event-State Persistence Repair

## Scope

R2 is a narrow runtime hotfix on top of the unchanged Research Kernel V2 introduced in R1. No model family, KPI, WFA/CPCV semantics, Factory research logic, Tournament, Monte Carlo, Forward, or Champion governance is changed.

## Owner-reported failure

`StreamlitValueAssignmentNotAllowedError` on `key="factory_auto_start"` when opening Discovery after the AUTO START button state had been persisted.

## Root cause

`persist_user_settings()` captures serializable Streamlit session state. R1 correctly classified `factory_start_btn` and dynamic lifecycle buttons as transient, but omitted the newer `factory_auto_start` key. Because persistence is invoked from the AUTO START click path, the button event could be written to `historical external: %LOCALAPPDATA%\ComplexPolicy\ModelLab\settings.json`. On a later process start, `ensure_state()` restored that value before `st.button(... key="factory_auto_start")` was created. Streamlit forbids assigning a button value through `st.session_state`, so widget creation failed.

## Repair

- `factory_auto_start` is now an explicit transient UI event and can never be saved/restored.
- `missing_*` disabled/action-placeholder button keys are also classified transient to close the same persistence class.
- Existing R1 settings containing these keys are scrubbed on load; Owner does not need to delete settings or API credentials.
- Added `UI_EVENT_STATE_PERSISTENCE` acceptance gate plus strengthened settings/background lifecycle tests.

## Non-regression rule

Button/event state is transient. Persisted state may contain durable operator choices, but not click events or lifecycle action widgets.
