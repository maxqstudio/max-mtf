# Agentic Research Learning V1 — v1.4.0

## Purpose

v1.4.0 adds three active research capabilities without creating a second scientific authority:

1. MAX Data Scientist Skill Pack — procedural methodology for any LLM Scientist.
2. Structured Research Memory — append-stable, typed experience extracted from committed hypothesis outcomes.
3. Deterministic Learning Policy — advisory ranking of the next scientific action from failure topology plus historical outcomes.

Future Embedder, RAG and RL surfaces exist only as disabled interfaces. They are intentionally fail-closed until a later version implements and validates them.

## Authority boundary

The learning stack may recommend **what to try next**. It may not:

- emit deterministic PASS/FAIL;
- change KPI thresholds or Strategy Champion execution authority;
- read/use protected Fresh/Locked/Shadow/Promotion evidence for adaptive learning;
- rank/promote Challengers as production authority;
- change risk or execute live trading.

Protected evidence never enters `MAX_RESEARCH_EXPERIENCE_V1`.

## Skill pack

Canonical path: `ModelLab/skills/max_scientist/`.

The pack contains one core skill and eight specialist skills. Every skill must contain PURPOSE, INPUT EVIDENCE, DECISION PROCEDURE, FAILURE PATTERNS, ALLOWED ACTIONS, FORBIDDEN ACTIONS, OUTPUT SCHEMA and REFERENCES. `ModelLab/skills/max_scientist/manifest.json` hashes each `historical external: SKILL.md`; hash drift fails closed.

## Structured Research Memory

`ModelLab/research/structured_research_memory.py` converts committed terminal hypothesis outcomes into typed experience rows. Supported, partially-supported, falsified and retired hypotheses can become learning evidence only when their source and decisive stage are not protected.

The experience ledger is de-duplicated by deterministic `experience_id` and produces aggregate statistics by action kind and originating failure gate.

## Learning Policy

`ModelLab/research/learning_policy.py` ranks bounded scientific action kinds such as selectivity, feature ablation, training-memory, model architecture, seed stability and regime policy. Ranking combines:

- historical structured outcome utility;
- exact failure-topology evidence when available;
- a small deterministic exploration prior.

The policy is advisory and cannot instantiate candidates directly. The LLM Scientist must still explain mechanism, expected observation and falsification; deterministic candidate validation remains authoritative.

## Future foundation

`ModelLab/research/future_learning_foundation.py` reserves stable interfaces for:

- `MAX_EMBEDDER_INTERFACE_V1`
- `MAX_RAG_INTERFACE_V1`
- `MAX_RL_POLICY_INTERFACE_V1`

All are `enabled=false` in v1.4.0. Enabling any of them raises `FUTURE_LEARNING_FOUNDATION_NOT_IMPLEMENTED`.

The structured experience schema is intentionally suitable as a future replay/embedding source, but v1.4.0 performs no vector embedding, semantic retrieval or reinforcement-learning reward update.

## Acceptance

Regression `R54_V140_AGENTIC_RESEARCH_LEARNING_FOUNDATION` must prove:

- skill quality/hash/zero-authority contract;
- protected-OOS exclusion from learning evidence;
- structured experience aggregation;
- contextual learning-policy ranking from actual historical statuses;
- no verdict/promotion/protected-OOS authority;
- disabled/fail-closed Embedder/RAG/RL foundations;
- Scientist/Supervisor integration.
