# MAX Research Agent v1.3.0 — LangGraph Agentic Scientist Migration

## Frozen control

v1.2.6 is immutable control baseline. ZIP SHA-256: `b27d42daefac0e427b38cbb94d4ab4bce117fb6d32767fc140110d28837473bc`. Strategy Champion and KPI authority are unchanged.

## Orchestration

AUTO Factory now enters `max_graph.factory_graph.run_auto_factory_graph()` and uses an explicit LangGraph state machine with SQLite checkpoints. The v1.2.6 custom orchestrator body remains only as a parity/acceptance reference. Mathematical/scientific stage engines are not rewritten into LLM logic.

## Agentic Scientist

The Model Research Scientist is a persistent Research Director graph. Each round performs guarded idempotency, deterministic attribution of prior proposal outcomes, bounded read-only evidence inspection, experiment design through the configured Scientist, deterministic proposal validation, and persistent hypothesis/proposal lineage. Scientist decides what to try; deterministic code decides whether it worked.

`SCIENTIST_DIRECTED` family/topology mode means Owner sets the allow-list; all allowed feasible families/topologies remain available throughout the Factory so structural/family/topology escape is real rather than confined to the initially selected subset. Scientist cannot mutate hard KPI, Strategy geometry, Locked/Fresh authority, CPCV seeds, live risk, symbol/date/timeframe, or promotion.

## Scientist Chat

Scientist Chat is a separate read-only LangGraph. It has no research execution, promotion, MT5, CPCV, Tournament, Monte Carlo or Forward edges. API keys are runtime closure inputs and never part of `ScientistChatGraphState` or checkpoint payloads.

## Persistence and dependencies

Pinned: `langgraph==1.2.11`, `langgraph-checkpoint-sqlite==3.1.1`. Checkpoint deserialization sets `LANGGRAPH_STRICT_MSGPACK=true`. Local build acceptance proves source/contracts; real LangGraph import, Factory `StateGraph` compile, SQLite checkpoint/reopen idempotency, and Scientist Chat secret non-persistence are run one-click by `ModelLab/RUN_LANGGRAPH_ACCEPTANCE.cmd`. The runner writes `historical external: evidence/current/LANGGRAPH_RUNTIME_ACCEPTANCE_v1_3_0.json` on PASS or FAIL with `first_failed_gate`; the runtime gate remains external when dependencies are unavailable in the build environment.

## Acceptance

New gates: `R48_V130_LANGGRAPH_ARCHITECTURE` and `R49_V130_AGENTIC_SCIENTIST_CONTRACT`. Full cumulative local source/contract target: 126/126 exact-tree PASS. Historical v1.2.6 scientific behavior is exercised in acceptance compatibility mode without changing production v1.3.0 LangGraph authority.
