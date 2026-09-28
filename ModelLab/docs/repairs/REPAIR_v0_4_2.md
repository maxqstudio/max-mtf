# Repair v0.4.2

Scope: presentation repair only plus live result-table plumbing. No model-selection formula, label policy, split, acceptance gate, Champion authority, or research hyperparameter bounds were changed.

## UI corrections

1. Live research area now has exactly three visible surfaces:
   - progress bar,
   - one live status line,
   - cumulative table with one row per completed model experiment.
2. Heartbeat messages update only the live status line. They are not duplicated into a technical log.
3. Completed candidate callbacks now carry structured `result_row` data so the table is generated from metrics, not parsed from UI text.
4. Table columns: Exp, Round, Model, Family, Score, PF, Exp R, Worst R, DD R, Trades, Fit s.
5. XGBoost, LightGBM, Random Forest, and disabled GRU selectors use fixed-height visible titles and label-collapsed toggles so all switches share one baseline.

## Acceptance performed locally

- Python source compile: PASS.
- Structured result-row emit present in Supervisor and Manual Research paths: PASS.
- Legacy heartbeat log surface removed from `progress_ui()`: PASS.
- Model selector alignment structure present for all four columns: PASS.

Streamlit browser rendering still requires runtime verification on the target Windows machine.
