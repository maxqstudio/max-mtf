# Research Control R1

## Status

Control-layer revision on top of **v0.7.5 R6**. It adds an explicit Owner choice between `AUTO` and `MANUAL` research without changing deterministic validation authority.

## AUTO contract

AUTO preserves the existing Factory path. LLM Research Scientist/Director can propose bounded experiments when configured; deterministic Discovery remains executable without LLM. All admission, chronology, capacity and PASS/FAIL decisions remain deterministic.

## MANUAL contract

MANUAL changes only candidate proposal/discovery authority.

- Owner supplies 1–8 exact candidates in the current UI.
- Supported families include deployable standalone and dynamic hybrid registry families.
- Exact candidate parameters are validated against legal registry bounds and hard capacity/resource authority before worker launch.
- Missing required parameters, illegal values or values that would be silently coerced fail closed.
- Manual size/topology sliders do not silently rewrite the exact candidate; hard capacity still wins.
- Exact take threshold is frozen as a single-value policy input; it is not searched.
- Autonomous research LLM is disabled in the compiled MANUAL runtime.
- Fidelity ladder, policy discovery, memory elite rechecks and automatic next-candidate generation are disabled.
- Deterministic validation remains: Full WFA → CPCV → Tournament → Monte Carlo → Fresh/Forward → Champion.
- Stage Scientist reports in MANUAL are deterministic `DISABLED_MANUAL_RESEARCH` records; no provider call occurs.
- No automatic research feedback/restart loop is allowed after MANUAL failure.

## Provenance

Every Factory manifest must expose `research_mode` and `research_control`. MANUAL evidence must state:

```json
{
  "research_mode": "MANUAL",
  "proposal_authority": "OWNER",
  "llm_used": false,
  "deterministic_discovery_used": false,
  "validation_authority": "DETERMINISTIC"
}
```

AUTO evidence must state deterministic discovery is enabled and keep existing R6 LLM/fallback semantics.

## Non-goals

MANUAL does not mean manual PASS/FAIL, manual leakage exceptions, disabled Data Quality, disabled CPCV, or bypass of Champion production KPI.
