# v0.7.5 R6 — Scientist Chat Clear Composer Hotfix 1

## Runtime defect
Owner Windows/Streamlit testing found that after **Clear Chat**, the visible history cleared but the Scientist Chat composer could remain disabled, preventing any new input.

## Root cause
The V2 component intentionally froze the composer with `root.dataset.resetting="1"` until Python returned a rotated persistent `thread_id` / `clear_epoch`. The clear event is observed only after the component render that produced it, so that first server rerun can still carry the old thread stamp. The implementation relied on a subsequent fragment rerun to deliver the new stamp. In real Streamlit runtime that follow-up rerun is not guaranteed to update the mounted component promptly, leaving the browser-side reset latch permanently set.

## Repair
- Clear remains a fail-closed, server-acknowledged thread-boundary operation.
- The frontend arms an immediate reset reconciliation pulse after Clear.
- While reset is unacknowledged, bounded reconciliation pulses request another server render (maximum 8 attempts per unchanged render sequence).
- A changed `thread_id::clear_epoch` stamp clears `resetting`, restores the composer, clears stale draft/history UI state, and resets the reconciliation counter.
- SEND is rejected client-side while `resetting==1`, so the old thread cannot receive a new message during the handshake.
- Existing backend stale-thread rejection remains unchanged as the second line of defense.

## Acceptance extension
`ModelLab/tests/stage10_scientist_chat_backend_contract_selftest.py` now includes the reset-handshake invariant and advances its internal adversarial assertions from **22/22** to **23/23**. The cumulative gate count remains **97** because this strengthens the existing Stage 10 gate rather than adding a new lifecycle stage.

## Additional authority defect found during audit
`governance/CURRENT_AUTHORITY.json.local_cumulative_acceptance` was stale at **96/96** while Stage 11 backend authority correctly declared **97/97**. Release-integrity tests did not compare these two authorities. The metadata is corrected to 97/97 and Stage 11 / RELEASE_SYNC regressions now require the local cumulative authority, backend cumulative declaration, and package manifest acceptance count to agree.

## Scope
No KPI, model topology, research lifecycle, Scientist routing, fallback policy, Factory execution authority, or Stage 12 contract is changed by this hotfix.
