# Repair v0.7.5 R6 — Scientist Chat State R1

## Owner-runtime defects

1. Provider/background worker could finish and commit `COMPLETED`, while the Scientist UI remained in `thinking` until the Owner pressed **Stop**. The Stop click merely forced a rerun; it was not supposed to be required to reveal a completed answer.
2. After **Clear Chat**, a later message could cause pre-clear chat to reappear. Streamlit V2 trigger values persist across reruns, while the old clear implementation removed the server-side nonce dedupe markers, allowing an old SEND payload to look fresh again.

## Root causes

- Scientist relied on fragment `run_every` as the only passive terminal reconciliation mechanism. This was not reliable enough with the mounted V2 custom component.
- Clear Chat reset history but did not own a persistent conversation generation identity. It also deleted `scientist_component_last_*` nonce markers, reopening stale event replay.
- `cancel_job()` could rewrite a terminal job if Stop arrived late.

## Repair contract

- Persistent `ScientistChatStore` schema is `MAX_SCIENTIST_CHAT_V2_THREAD`.
- Each store owns a persistent `thread_id`.
- Clear atomically empties history **and rotates `thread_id`**.
- SEND/STOP/poll events and background jobs carry `thread_id`.
- Stale-thread SEND events and stale job results are rejected/discarded.
- Store writes with a stale thread fail closed with `STALE_SCIENTIST_CHAT_THREAD`.
- Terminal `COMPLETED/FAILED/CANCELLED` job state is immutable.
- Pending custom component emits a bounded ~650 ms client reconciliation pulse; this forces server settlement of terminal results without an Owner Stop click.
- Component freezes composer during Clear until the rotated server thread returns.
- Existing nonce dedupe markers are retained across Clear.

## Acceptance

- New gate: `R21_SCIENTIST_CHAT_STATE_RECONCILIATION` / `ModelLab/tests/scientist_chat_state_selftest.py`.
- Scientist Knowledge workflow audit adds terminal reconciliation + clear-thread isolation checks.
- Fresh cumulative acceptance: **86/86 PASS**, `first_failed_gate = null`.
- Scientific model/research authority remains **v0.7.5 R6**; Research Control remains **R1**; Scientist Knowledge remains **R1**.

## External truth

Owner Windows Streamlit visual/runtime remains a separate evidence gate. Local selftests do not substitute for real UI behavior.
