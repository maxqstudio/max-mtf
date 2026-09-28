# Max MTF v2.0.1 — MTF-1 R5 Closure Proof Hardening

## Purpose

R4 scientific/data implementation is accepted. R5 changes **closure proof integrity only**. It must not alter MTF resampling, chronology, KPI, CPCV, model bounds, promotion authority, Strategy Optimizer semantics, or Scientist recovery behavior.

## Final closure verifier contract

`ModelLab/acceptance/verification/VERIFY_MTF1_FINAL_CLOSURE.cmd` is the canonical final decision path. It invokes `ModelLab/mtf/mtf1_final_closure.py`, which may emit `MTF_1_CLOSED` only when all of the following are simultaneously valid for the exact current candidate:

1. **Local acceptance proof**
   - schema = R5 acceptance schema;
   - exact ordered 51 `(gate, script)` rows equal `run_acceptance.TESTS`;
   - no duplicates;
   - every result `PASS`;
   - every `exit_code == 0`;
   - `first_failed_gate == null`;
   - current source-tree signature and suite signature match;
   - execution mode = `FRESH_FULL` for external closure;
   - external-gate snapshot equals the canonical registry.
2. **Owner MT5 proof**
   - candidate binding matches exact tree/suite/local-acceptance SHA/external-registry SHA/EA identity/Owner config SHA;
   - terminal data root proof present and PASS;
   - broker/server/terminal provenance present;
   - symbol and valid UTC window present;
   - native M5/M15/H1/H4 row counts all positive;
   - M15/H1/H4 M5-derived parity PASS with zero failed bars;
   - Real Volume mode is exact-required or explicit zero-only unavailable, with zero Real Volume failures;
   - Data Quality PASS;
   - causal alignment PASS with zero future-close violations and zero primary-close mismatch;
   - lineage manifest preview exists and `bundle_identity_sha256` recomputes exactly.
3. **MetaEditor proof**
   - exact active EA project-relative identity/SHA/version matches candidate;
   - deployed MQ5 SHA equals canonical EA SHA;
   - MetaEditor tool identity is recorded;
   - exact compile command is recorded;
   - compiler summary explicitly reports zero errors;
   - expected EX5 was absent immediately before compile and exists after compile;
   - archived EX5 SHA matches evidence;
   - archived compile-log SHA matches evidence;
   - evidence is bound to the same exact candidate and MetaEditor config SHA.
4. **Canonical external requirements** remain locked:
   - `OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY = REQUIRED_ON_OWNER_MACHINE`
   - `OWNER_MT5_TERMINAL_DATA_ROOT_DETECTION = REQUIRED_ON_OWNER_MACHINE`
   - `METAEDITOR_MAX_MTF_V2_COMPILE = REQUIRED_ON_OWNER_MACHINE`
   - `MTF_STRATEGY_RUNTIME = NOT_APPLICABLE_MTF1`

The final closure evidence is `historical external: owner_acceptance/evidence/mtf1/OWNER_MTF1_FINAL_CLOSURE.json`. Changing any bound local/Owner/MetaEditor evidence invalidates existing final closure proof.

## One-click flows

- `ModelLab/RUN_MTF1_OWNER_ACCEPTANCE.cmd`: fresh 51-gate acceptance → Owner MT5 parity/root proof → evidence readback verification.
- `ModelLab/RUN_MTF1_METAEDITOR_ACCEPTANCE.cmd`: fresh 51-gate acceptance → exact EA MetaEditor compile → fresh EX5 archive → evidence readback verification.
- `ModelLab/RUN_MTF1_FINAL_CLOSURE.cmd`: fresh 51-gate acceptance → Owner MT5 proof → MetaEditor proof → final closure verifier.

## New local gates

- `V201_LOCAL_ACCEPTANCE_RESULT_INTEGRITY`
- `V201_OWNER_EVIDENCE_PROOF_COMPLETENESS`
- `V201_METAEDITOR_FINAL_CLOSURE_WIRING`

Expected local result: **51/51 PASS**, `first_failed_gate=null`.

## Phase boundary

A local 51/51 PASS does **not** close MTF-1. Until real Owner MT5 and MetaEditor evidence validate, final state remains:

```text
MTF-1 FINAL CLOSED : NO
MTF-2              : BLOCKED
```
