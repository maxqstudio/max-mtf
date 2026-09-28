# Max Research Agent — ONNX Factory
## R4 Hotfix5 — Scientist Chat Hard Reset & Request Budget

Authority: **v0.7.5 R6**

## Proven defect

Owner runtime reported Scientist Chat could remain in a long thinking cycle, finish without a visible answer, show no provider usage increase, and **Clear Chat** itself became unreliable. Long persistent history was suspected.

## Repair

1. **Clear Chat is now a hard thread reset**
   - cancels an active Scientist worker first;
   - cleans its request artifact;
   - atomically replaces per-Factory history with an empty canonical store instead of deleting the history file;
   - clears error/notice/pending state;
   - rotates a frontend `clear_epoch`;
   - drops stale Scientist component event nonces.
2. **Frontend clear is immediate**
   - history becomes empty immediately;
   - thinking/error/optimistic rows are removed;
   - draft and sessionStorage draft are cleared;
   - controls are re-enabled while backend reset completes.
3. **Long chat cannot bloat one provider request indefinitely**
   - persistent UI history remains up to 80 messages;
   - provider request history is capped to newest <=16 messages and <=28,000 chars;
   - read-only research context is capped to 60,000 chars;
   - current user prompt is capped to 12,000 chars.
   This separates *visible conversation history* from *model request context*.

## Targeted acceptance

- Python compile: PASS
- `ModelLab/tests/scientist_chat_reset_selftest.py`: PASS
- `ModelLab/tests/scientist_chat_request_budget_selftest.py`: PASS
- `ModelLab/tests/scientist_chat_ui_selftest.py`: PASS
- `ModelLab/tests/scientist_chat_ai_ux_selftest.py`: PASS
- `ModelLab/tests/scientist_chat_readonly_selftest.py`: PASS
- `ModelLab/tests/scientist_context_parity_selftest.py`: PASS
- `ModelLab/tests/interaction_state_selftest.py`: PASS
- `ModelLab/tests/ui_event_state_selftest.py`: PASS
- `ModelLab/tests/llm_availability_fallback_selftest.py`: PASS
- `ModelLab/tests/factory_background_selftest.py`: PASS
- topology / deterministic Discovery / creativity / family-size / CPCV seed / Data Quality targeted gates: PASS
- research core preservation: **21/21 byte-identical**

## Important limitation

This repair makes chat reset deterministic and bounds request size, but the Owner's earlier observation that provider usage did not increase is **not yet proven to be caused by long history**. If a fresh chat still thinks and returns no answer, the next authority is the Scientist worker log/job JSON; do not blame UI or history without that evidence.
