# MTF-1 R6 — External Execution Proof

## Status

R6 hardens only the external closure evidence layer. MTF-1 scientific/data behavior is frozen from R5/R4. MTF-2 remains blocked until actual Owner MT5 and MetaEditor execution evidence passes the R6 production verifiers.

## Threat model and boundary

R6 does not claim hardware or OS cryptographic attestation. It closes the practical internal-evidence defect where a consistent JSON summary, synthetic frames, or arbitrary bytes named `.ex5` could previously satisfy closure. The verifier must derive conclusions from archived raw execution artifacts and current configured external tools instead of trusting caller-supplied summaries.

## Shared closure run identity

`ModelLab/mtf1_closure_run.py --start` creates `historical external: owner_acceptance/runtime/MTF1_CLOSURE_RUN.json` containing a random 32-hex `closure_run_id`. Fresh local acceptance records it. Owner MT5 evidence, MetaEditor evidence, and final closure evidence must carry the same value. Checkpoint resume from another run is not compatible.

## Owner MT5 proof

The Owner runner archives the exact native MT5 inputs used in the execution under:

`owner_acceptance/evidence/mtf1/owner_runtime/<closure_run_id>/`

Required artifacts include native M5, M15, H1, H4 CSV files and MT5 runtime provenance. Each artifact is SHA-bound and normalized-data-hash-bound.

Existing-evidence verification reloads the archived bars and deterministically recomputes:

- canonical M15/H1/H4 from M5;
- native higher-TF OHLCV parity;
- Real Volume parity policy;
- causal alignment and violation counts;
- MTF Data Quality;
- lineage manifest;
- bundle identity.

Production verification then performs live revalidation from Owner MT5 for the exact symbol/window and rejects any native-input hash or broker/server/terminal provenance mismatch. Synthetic archives that do not match the real Owner terminal cannot close MTF-1.

## MetaEditor proof

The MetaEditor runner validates the configured executable, copies the exact canonical EA to the verified terminal data root, removes stale output, invokes MetaEditor with the exact compile command, requires the subprocess return code to be exactly `0`, archives the resulting log and EX5, and records the process execution window.

Existing-evidence verification independently:

- resolves the currently configured MetaEditor installation;
- hashes the actual executable;
- checks the exact deployed MQ5 hash against the active EA;
- validates exact command argv;
- reparses the archived compile log instead of trusting `compile_summary`;
- requires zero parsed compile errors and source-filename evidence in the log;
- verifies archived log/process-record/EX5 hashes;
- rejects non-binary-like or implausibly small fake EX5 payloads;
- requires the EX5 creation timestamp to fall within the recorded compile execution window.

## Generation versus verification

Generation and verification are separate authorities.

- `ModelLab/RUN_MTF1_FINAL_CLOSURE.cmd` may create new evidence.
- `ModelLab/acceptance/verification/VERIFY_MTF1_FINAL_CLOSURE.cmd` calls only `python mtf1_final_closure.py --verify-existing`.
- Read-only verification hashes existing final evidence before and after verification and fails if it changes.

A corrupted existing final evidence file must remain corrupted and fail; VERIFY must never overwrite it.

## R6 local adversarial gates

R6 adds:

- `V201_OWNER_RAW_REPLAY_AUTHENTICITY`
- `V201_METAEDITOR_EXECUTION_ARTIFACT_AUTHENTICITY`
- `V201_METAEDITOR_LOG_REPARSE_AUTHORITY`
- `V201_METAEDITOR_PROCESS_EXITCODE_AUTHORITY`
- `V201_FINAL_VERIFY_READ_ONLY`
- `V201_CLOSURE_RUN_ID_BINDING`

Local target becomes **60/60 PASS**. Local PASS remains necessary but not sufficient for final MTF-1 closure.
