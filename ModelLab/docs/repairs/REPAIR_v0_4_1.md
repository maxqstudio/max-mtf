# Repair v0.4.1 — progress UI deduplication

Scope: presentation-only. No model, label, split, scoring, governance, or hyperparameter logic changed.

## Defect
During a long fit the same heartbeat was visible three times: in the progress-bar text, in a blue status box, and repeatedly in the technical log.

## Repair
- progress bar is visual-only;
- exactly one live training-status line is visible;
- technical log moved under a collapsed `Detail teknis` expander;
- `fit_heartbeat` messages update the live line but are not appended to log history;
- milestone messages (fold start/done, candidate done, round transitions, errors) remain in technical history;
- completion uses the same live-status placeholder instead of adding another duplicate progress label.

Research engine lineage remains v0.4.
