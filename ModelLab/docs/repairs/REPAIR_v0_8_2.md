# REPAIR v0.8.2 — Optimizer recovery UI + Scientist provenance

v0.8.2 repairs Owner-runtime defects exposed after atomic MT5 report recovery.

- `RESUME FROM MT5 REPORT` and `RECOVER LATEST MT5 RESULT` use a legal app-scope Streamlit rerun when invoked from script/fragment bodies. Fragment-key reruns remain reserved for widget callbacks.
- Scientist Optimizer Report reads `scientist_assist` from the frozen run request, never mutable live UI state.
- Deterministic-only refinement is distinct from deterministic fallback. Every fallback records a reason; Scientist failures preserve error provenance without relaxing KPI.
- `NO_CHAMPION` displays the frozen Owner KPI values and near-miss ranking uses the same per-row frozen requirements.
- Legacy XML recovery is hidden once current evidence has already reached `NO_CHAMPION` or `CHAMPION_FOUND`, preventing duplicate recovery jobs.
- No KPI is relaxed and no MT5 round is repeated by this repair.
