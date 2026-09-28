# Scientist Chat Read-Only V1

## Purpose
`Scientist Chat` is a manual discussion room for the Owner. It is not a second research agent.

## UI contract
- right-side show/hide workspace;
- manual model selection independent from the autonomous Research Scientist route;
- panel width presets: Compact / Balanced / Wide;
- context scopes: AUTO, Current Factory, Current Generation, Model & Candidates, Data Quality, Scientist Memory;
- fallback is OFF by default for manual exact-model semantics;
- chat history is stored per Factory outside research evidence.

## Authority boundary
Scientist Chat may read a bounded snapshot of committed research evidence and explain, critique, compare, diagnose, or recommend ideas. It has no tools and no execution authority.

It cannot:
- start, pause, stop, abort or resume research;
- modify configuration or a frozen research plan;
- admit/reject candidates;
- write research evidence;
- call MT5 or compile models;
- promote a Champion;
- change KPI/risk/research authority.

The module intentionally does not import Factory/Champion/job execution modules.

## Context boundary
The read-only context may include Factory identity/status, frozen research plan, Owner size/topology authority, Data Quality, hardware/capacity profile, committed Discovery/WFA evidence, candidate pool, CPCV/Tournament/Monte Carlo summaries, failure topology, Scientist/Director journals, and bounded research memory.

Raw training rows, API credentials, execution endpoints, and locked/fresh Forward evidence unavailable to the running Scientist are excluded.

## LLM routing
The selected chat model is manual. With fallback OFF, failure of that exact model is surfaced to the Owner. If fallback is explicitly enabled, only retryable quota/rate-limit/timeout/model-unavailable/provider-5xx conditions advance through the configured fallback stack. Authentication/configuration/malformed-request failures remain fail-closed.

Chat calls do not mutate autonomous Scientist model-health state.

## Provenance
Every assistant message records requested model, actual answering model, fallback usage, token usage when available, and the read-only evidence source IDs used to build its context.


## R2 extension — streaming and per-model profiles

R2 preserves every read-only boundary above and adds per-model discussion profiles, safe process telemetry, provider SSE streaming where supported, same-model buffered compatibility fallback, idempotent request IDs, actual answering-model provenance, and the `RESEARCH SETTINGS` context scope. Raw hidden chain-of-thought remains excluded. See `ModelLab/docs/ui/SCIENTIST_CHAT_R2_STREAMING_CONTRACT.md`.
