# LLM Scientist R1 — Autonomous Research Authority

**Scope:** autonomous Research Scientist / Research Director used by AUTO Factory. Scientist Chat is a separate read-only surface and is not governed by this runtime routing contract.

## Hard authority

- Deterministic code owns PASS/FAIL, chronology, KPI gates, candidate identity, stage promotion and Champion promotion.
- LLM `stop_research` is advisory only. It cannot stop Discovery, cancel failure learning, lower gates or promote a candidate.
- LLM dataset context is schema/header plus committed aggregate evidence only. Raw CSV rows and current-cycle sealed Tournament/Monte-Carlo/Fresh evidence are excluded from tuning context.
- Every concrete candidate is revalidated by `effective_bounds` and the deterministic capacity contract before training.
- Research memory is keyed by exact research-contract hash. Corrupt global memory fails closed rather than silently resetting.

## Ordered routing

- START RESEARCH performs an ordered route preflight.
- Fallback is allowed only for retryable availability failures: quota/rate-limit, timeout, provider 5xx, model unavailable, or provider connection unavailable.
- Authentication, malformed requests/config, generic endpoint 404, parsing/programming errors and deterministic errors fail closed.
- Route health identity is provider + model + endpoint + API-key environment identity. Separate accounts/endpoints using the same model cannot poison each other's cooldown.
- Health persistence uses a cross-process file lock plus atomic replace.
- If all retryable routes are exhausted at START, the current Factory Discovery invocation latches deterministic-only mode and does not retry the exhausted stack inside downstream Director/Scientist/Supervisor calls for that invocation.
- If all routes exhaust during a Supervisor round, the remaining rounds continue deterministically without re-hammering the exhausted routes.

## Compatibility and provenance

- Legacy `_call(messages)` Scientist doubles are selected by signature inspection before invocation. An internal `TypeError` is never interpreted as a legacy-signature mismatch and can never cause a duplicate provider request.
- Every successful/fallback call records selected priority/provider/model, attempts, usage/cost provenance and health snapshot where enabled.
- Secrets are never written to provenance/health evidence.

## Failure learning

- Pool/CPCV/Tournament/Monte-Carlo failure learning remains bounded by exposure authority and exact-contract memory.
- LLM stop requests cannot suppress an otherwise actionable committed lesson.
- When the LLM is unavailable/exhausted, deterministic failure topology may continue research without granting the LLM any execution authority.

## Acceptance

Dedicated gate: `ModelLab/tests/stage9_llm_scientist_backend_contract_selftest.py`.
Cumulative authority after integration: **95/95 PASS** on exact-tree closure with Scientist Knowledge synchronized. Stage 9 is **CLOSED**; Stage 10 Scientist Chat is next.
