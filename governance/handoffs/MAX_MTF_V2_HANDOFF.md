# Max MTF v2 — Handoff

Current build: **MAX MTF v2.0.1 / MTF-1 External Execution Proof**. Local acceptance target is **75/75 PASS**. MTF-2 remains blocked until the final closure verifier accepts actual Owner MT5 and MetaEditor execution evidence from one shared closure run.

## Non-negotiable MTF-1 contracts

1. Current scientific/data logic is preserved; this phase hardens external proof-of-execution and closure verification only.
2. Local acceptance must contain exact ordered 75 gate/script results, all PASS/exit 0; external closure requires `FRESH_FULL`.
3. `closure_run_id` is shared across fresh local acceptance, Owner runtime evidence, MetaEditor evidence and final closure evidence. Evidence from different runs cannot be mixed.
4. Owner proof must archive actual native M5/M15/H1/H4 input artifacts and MT5 provenance. Verification replays the archive deterministically and production verification re-fetches the exact same Owner MT5 window.
5. MetaEditor proof must validate the current configured MetaEditor executable/hash, exact canonical/deployed MQ5 and command, reparse the archived compiler log, enforce process return code exactly zero, verify process record and archived EX5. Caller-supplied summary fields are not proof authority.
6. `ModelLab/acceptance/verification/VERIFY_MTF1_FINAL_CLOSURE.cmd` is read-only and invokes only `mtf1_final_closure.py --verify-existing`.
7. Bounded Scientist JSON recovery remains exactly one format-only retry at temperature 0; a second malformed response fails closed.
8. MTF-2 functionality is not enabled in this phase.
9. Selective inherited fixes remain active: canonical Strategy geometry cannot be overridden by stale candidate metadata; MaxHold is a minimum purge/embargo guard and must not reduce stricter upstream values; only explicitly proven geometry-mismatch FAILED jobs can RESUME; live CPCV KPIs are provisional telemetry only.


Scientist Python Analysis Runtime V1 is an optional MTF-1-side analytical support capability only. It uses a dedicated user-local interpreter and one shared guarded host executor for autonomous Scientist/Director and Scientist Chat. It does not start MTF-2 and does not alter deterministic admission/promotion/training/acceptance authority.
- Integrated Scientist Python Owner Windows acceptance is now in-candidate: `ModelLab/RUN_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd` drives setup -> health -> fresh 75-gate acceptance -> live guarded-runtime/security checks -> `--verify-existing`; evidence is `historical external: owner_acceptance/evidence/scientist_python/OWNER_SCIENTIST_PYTHON_RUNTIME_ACCEPTANCE.json`. Owner runtime is not READY until this live evidence passes.
- Security authority: generated scientific imports are capability proxies, not raw modules; mandatory runtime acceptance includes transitive ctypes/native file/process/network escape proofs and legitimate-analysis regression.

Historical revision documents remain evidence history and are not current build identity.

## v2.0.1 ModelLab canonical layout migration

Current source layout authority is `ModelLab/governance/MODELLAB_LAYOUT_MANIFEST.json`. `ModelLab/` root contains only the nine operator CMD launchers; Python/config/requirements/verifier/setup/tool implementation is domain-packaged below the root. The migration is path/import/launcher-only and does not alter scientific semantics. MTF-2 remains blocked.
