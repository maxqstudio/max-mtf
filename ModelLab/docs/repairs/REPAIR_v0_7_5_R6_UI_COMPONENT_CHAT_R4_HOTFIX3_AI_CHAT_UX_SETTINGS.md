# Max Research Agent — ONNX Factory
## R4 Hotfix3 — AI Chat UX + Read-only Research Settings Context

Scientific authority remains **v0.7.5 R6**.

### Bounded scope
- LeftNav header: remove Streamlit `st.columns` dependency; fixed brand + anchored hide control.
- Scientist Chat thinking state: optimistic user turn + visible animated `Scientist is thinking` indicator while a request is in-flight.
- AI-chat formatting: responsive Markdown headings, lists, quotes, code, links and tables inside the isolated Scientist component.
- Grounding: forbid invented warning causes/details; strip explicit hidden-reasoning wrappers before display.
- Research settings visibility: Scientist Chat receives a sanitized, read-only snapshot of current Owner research configuration and may recommend changes.
- New Chat context scope: `RESEARCH SETTINGS` / `SETTINGS`.

### Settings authority
Scientist Chat can read and discuss:
- label and split contracts;
- deterministic acceptance/KPI configuration;
- topology and per-family size priorities;
- compute/capacity preferences;
- search creativity/influence and experiment budgets;
- policy/window discovery, fidelity ladder, experiment blocks and research memory controls;
- enabled model-family configuration;
- non-secret autonomous Scientist routing identity.

It cannot modify any setting. Credentials, API keys/tokens/passwords and secret-like fields are removed.

For an active Factory the chat receives both:
1. **CURRENT OWNER CONFIG** — useful for recommendations/future Factory starts; and
2. **FROZEN ACTIVE `research_plan`** — authority for the running Factory.

The prompt requires the Scientist to distinguish the two and state when a recommendation only applies to the next Factory.

### Recommendation contract
When asked how settings should change, Scientist should prefer:

| Current | Suggested | Why | Trade-off / Effect |
|---|---|---|---|

Recommendations may never lower scientific hard gates merely to manufacture survivors and may not bypass Capacity Governor, fixed CPCV seed authority, or locked/fresh Forward separation.

### Local targeted evidence
PASS:
- `ModelLab/tests/scientist_chat_settings_context_selftest.py`
- `ModelLab/tests/scientist_chat_ai_ux_selftest.py`
- `ModelLab/tests/scientist_chat_readonly_selftest.py`
- `ModelLab/tests/scientist_chat_ui_selftest.py`
- `ModelLab/tests/responsive_shell_selftest.py`
- `ModelLab/tests/settings_persistence_selftest.py`
- `ModelLab/tests/topology_priority_selftest.py`
- `ModelLab/tests/family_size_priority_selftest.py`
- `ModelLab/tests/family_size_priority_e2e_selftest.py`
- `ModelLab/tests/cpcv_seed_confirmation_selftest.py`
- `ModelLab/tests/data_quality_authority_selftest.py`
- `ModelLab/tests/llm_availability_fallback_selftest.py`

Research/scientific core files outside the intentional chat/UI boundary remain byte-identical to Hotfix2; see `historical external: UI_COMPONENT_CHAT_R4_HOTFIX3_BACKEND_PRESERVATION.json`.

### Runtime truth
This does **not** claim visual acceptance on the Owner machine. Visual chat quality remains governed by real runtime evidence/screenshots.
