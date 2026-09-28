# Scientist Chat R2 — Streaming & Model Profiles

## Authority

Scientist Chat remains **read-only**. R2 changes interaction quality and model-specific discussion controls, not research mutation authority.

## Per-model profile

Each selectable Chat model may persist its own discussion profile: analysis depth (`QUICK/BALANCED/DEEP`), temperature, request timeout, max output tokens, research-context character budget, history message/character budget, streaming preference and same-model buffered compatibility fallback.

These profiles are independent from the autonomous Research Scientist ordered model stack.

## Streaming contract

When the selected provider exposes OpenAI-compatible SSE, visible answer chunks are committed to the background Chat job and surfaced incrementally. Operational phases are:

`QUEUED → BUILDING_CONTEXT → CALLING_MODEL → WAITING_FIRST_TOKEN → STREAMING → COMPLETED`

Terminal alternatives are `FAILED`, `CANCELLED`, and hard timeout. No job is allowed to remain thinking forever after worker death/timeout.

If an endpoint rejects/ignores streaming, an explicitly enabled **same-model** buffered compatibility request may be used. This is not a routing fallback and cannot silently change the selected model.

## Reasoning visibility

The UI may show safe process summaries such as “Reading research evidence” or “Waiting for first token”. Raw provider hidden reasoning / chain-of-thought is excluded and explicit `<thought>`/reasoning wrappers are sanitized from visible text.

## Idempotency

Every send event carries a request/event nonce. One request ID may create at most one persisted user turn and one background job. Streamlit reruns/replayed component events must be ignored.

## Provenance

Each completed assistant turn stores requested model, actual `answered_by`, provider, fallback usage, attempts, usage/cost telemetry where available, process steps, profile snapshot and context source IDs.

## Context

`RESEARCH SETTINGS` is a valid context scope. The model may compare current Owner configuration with the frozen active plan and recommend changes, but cannot apply them. Credentials and execution endpoints are stripped.
## Max-native knowledge and novelty guard

Scientist Chat always receives a compact `max_knowledge` snapshot derived from `ModelLab/scientist/knowledge/SCIENTIST_KNOWLEDGE_BASE.json`. This static map describes Max capabilities and workflow contracts; it is not live-stage PASS evidence.

Before substantive feature/workflow recommendations the Scientist must identify overlap with existing Max capability and classify the idea as `EXISTING`, `EXTENSION`, `EXPERIMENT`, `NEW`, `CONFLICT`, or `OUTSIDE_CURRENT_CONTRACT`. Scientist may recommend beyond Max, but must not propose rebuilding a capability that already exists without first identifying the exact new gap.

The knowledge database is release-governed by `ModelLab/tests/scientist_knowledge_sync_selftest.py`; stale source/doc provenance fails cumulative acceptance.



## Chat State R1 amendment

Runtime evidence exposed two state defects that are now explicit contract failures:

1. A background provider job may reach `COMPLETED` while the V2 component remains visually `thinking`; the terminal result must be reconciled automatically without requiring the Owner to press **Stop**.
2. `Clear Chat` must create a new conversation generation. A stale pre-clear SEND trigger or late worker result must never repopulate the cleared history.

Required state contract:

- Every persistent chat store owns a `thread_id`.
- `Clear Chat` atomically empties history **and rotates `thread_id`**.
- SEND/STOP/Clear events and background jobs carry `thread_id`; the hidden reconcile state is rerun-only and does not own message identity.
- The server rejects stale-thread SEND events and discards/cancels stale-thread jobs.
- Persistent store writes with a stale thread id fail closed with `STALE_SCIENTIST_CHAT_THREAD`.
- `COMPLETED`, `FAILED`, and `CANCELLED` job states are terminal and immutable; a late Stop cannot rewrite a completed response.
- While a job is pending the custom component updates a hidden `reconcile` state on a recurring bounded cadence (~650 ms). The heartbeat is an interval tied to the current `pending_job_id`, not a one-shot timer: if one browser/V2 state notification is coalesced or lost, the next heartbeat retries automatically until the server reports a terminal state. `on_reconcile_change` follows the same V2 state-callback path as model/context/fallback and forces a Scientist-fragment rerun so `partial_text` and terminal status are observed without pressing Stop. The legacy `poll` trigger and `on_poll_change` callback remain forbidden because they caused the Owner-runtime drawer mount regression.
- `Clear Chat` uses the already-supported `on_clear_change` callback to queue the clear before the resulting fragment body renders. The server atomically rotates the persistent thread first, so the next component payload already carries the new `thread_id/clear_epoch`; Clear does not depend on a second render to establish the thread boundary.
- During Clear-thread rotation, the textarea remains writable but SEND remains fail-closed until the new server-authoritative `thread_id/clear_epoch` arrives. Text typed during that interval is preserved rather than discarded when the new thread is acknowledged.
- The response becomes canonical only after the server settles the matching current-thread terminal job into `ScientistChatStore`.
- Client optimistic/thinking/streaming rows remain presentation only and never own history authority. Streaming text is revealed only from worker-received `partial_text`, with a visible typing cadence rather than dumping a large received chunk at once.

Acceptance authority: `ModelLab/tests/scientist_chat_state_selftest.py` plus cumulative `ModelLab/acceptance/runners/run_acceptance.py`.


## Stage 10 backend integrity amendment

Stage 10 hardens the existing read-only Scientist Chat without expanding its authority. The backend contract now requires:

- persistent chat load/save/clear operations for one Factory are cross-process locked and atomic-replace; stale-thread writes fail closed and corrupt JSON is surfaced as corruption, never silently reset;
- `request_id` is a backend idempotency key across tabs/processes, so one request cannot create two workers;
- job terminal state uses monotonic compare-and-set semantics: `COMPLETED`, `FAILED`, and `CANCELLED` cannot overwrite one another after the first terminal commit; hard timeout has one canonical terminal transition;
- provider signature compatibility is resolved before invocation; an internal provider `TypeError`, auth error, programming error, or post-init timeout cannot cause an automatic duplicate request;
- stream-to-buffered compatibility is allowed only for explicitly classified pre-answer stream-capability failure, exactly once;
- explicit Chat fallback preserves the complete route identity (`provider`, `model`, `base_url`, `api_key_env`, route id), and the actual answering model owns its own timeout/token/context budget;
- CPCV, Tournament, and Monte Carlo evidence is exposed as deterministic truth only after terminal-seal and artifact-hash verification; tampered/malformed evidence fails closed;
- successful assistant turns persist actual provider/answering route/fallback/usage-cost provenance when available; cost is never invented;
- hidden/internal failed assistant rows are excluded from future model conversation history;
- STOP losing a race to an already-committed `COMPLETED`/`FAILED` result must reconcile that terminal result instead of discarding it.

Dedicated Stage 10 authority: `ModelLab/tests/stage10_scientist_chat_backend_contract_selftest.py`. Existing R17/R19/R21 Chat tests remain regressions and do not substitute for the concurrency/tamper gate.

## Live hardware truth amendment

Scientist Chat must know the **current host** before a Factory exists. Owner compute settings such as `allow_cuda`, `allow_rocm`, `allow_vulkan`, or `allow_opencl` are policy allowances only; they are never evidence that the corresponding accelerator/runtime is present or usable.

Every new Scientist Chat request therefore carries two read-only sources independent of Factory state:

- `LIVE_HW` — current-host detected CPU, physical/logical/planning cores, RAM, GPU/VRAM, OS class, Torch installation/CUDA availability, and hardware profile hash.
- `LIVE_COMPUTE` — effective compute plan resolved from current detected runtime capabilities plus Owner policy, including the actual temporal/XGBoost/LightGBM/RandomForest backends and compact accelerator capability truth.

These sources are available even when `factory.status = NO_FACTORY_CONTEXT`. If a Factory already exists, live host truth remains distinct from the frozen `historical external: hardware_profile.json` / `historical external: research_plan.json` used by that Factory.

Scientist must:

- use `LIVE_HW` / `LIVE_COMPUTE` directly when recommending pre-research model families or compute settings;
- not ask the Owner to repeat hardware specifications already present in those sources;
- not infer a GPU from configured accelerator allowances;
- explicitly distinguish current-host capability, current Owner settings, and frozen active Factory plan.

Hardware collection remains read-only and contains no API credentials or execution authority.
