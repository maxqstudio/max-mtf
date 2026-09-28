# MAX MTF v2.0.1 — Owner Acceptance Post-Seal Evidence + Exit-Code Authority Repair

Build scope: `MAX_MTF_V2_0_1_OWNER_ACCEPTANCE_POSTSEAL_EVIDENCE_AND_EXITCODE_REPAIR`.

This repair separates volatile current acceptance identity from immutable build-history evidence. `historical external: BUILD_ACCEPTANCE_v2_0_1.json` is the canonical fresh-run report, `historical external: CANDIDATE_BUILD_v2_0_1.json` is the single mutable current acceptance claim, and `historical external: CURRENT_EVIDENCE_SYNC_v2_0_1.json` records the latest synchronization. Repair/selftest evidence sealed by a prior build belongs under `ModelLab/evidence/history/build_repairs/` and is never rebound to later Owner report SHA values.

`sync_current_build_evidence()` may rotate the current report SHA for repeated `FRESH_FULL` runs on the same exact source tree and suite. Source-tree signature, suite signature, gate count, ordered 75-result PASS/exit-zero contract, and `FRESH_FULL` execution mode remain fail-closed.

The Scientist Python Owner CMD and verify-existing CMD use label-based bootstrap selection. Child `%ERRORLEVEL%` is captured outside parenthesized command blocks. Exit code 0 yields PASS; every nonzero child code is preserved as FAIL; bootstrap-unavailable remains exit code 103. Delayed expansion is not used.

Scientific semantics, model capacity, CPCV/WFA/Tournament/Monte Carlo/Forward/MoE, MT5/MetaEditor semantics, and ModelLab layout are unchanged. MTF-2 remains BLOCKED pending live Owner Windows acceptance.
