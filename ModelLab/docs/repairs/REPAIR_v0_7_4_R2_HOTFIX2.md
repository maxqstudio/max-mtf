# CPMF v0.7.4 R2 Hotfix2 — Streamlit Widget State

## Defect
Advanced -> Compute backend could crash with `StreamlitValueAssignmentNotAllowedError` for `compute_rescan` because the transient `st.button` event was persisted/restored as ordinary widget state.

## Repair
- `compute_rescan` is explicitly transient in `settings_store.is_persistable_ui_key()`.
- Existing persisted settings containing `compute_rescan` are scrubbed automatically by `sanitize_ui_state()` during load.
- All current `st.button` keys were audited and are covered by transient exact/prefix policy.
- Latest compact sidebar Research action-only UI is preserved.
- R2 Hotfix1 Windows-safe ONNX artifact-path repair is preserved.

## Targeted acceptance
- Python compile: PASS.
- `compute_rescan` persist/restore exclusion: PASS.
- stale settings auto-scrub: PASS.
- all current button keys transient-policy audit: PASS (18/18).
