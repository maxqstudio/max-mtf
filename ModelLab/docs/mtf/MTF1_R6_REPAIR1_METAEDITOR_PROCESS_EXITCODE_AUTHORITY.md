# MTF-1 R6 Repair 1 — MetaEditor Process Exit-Code Authority

Scope is limited to the R6 MetaEditor external execution-proof layer. Scientific/data behavior, Owner MT5 evidence, closure-run binding, raw replay, live revalidation, and read-only final verification are unchanged. MTF-2 remains blocked.

## Defect

R6 recorded `compile.process_returncode` and the archived process record `process_returncode` but did not make either field authoritative. A non-zero MetaEditor process return code could therefore be accepted when the archived compiler log reported zero errors and the EX5 fixture otherwise validated.

## Repair contract

- Compile generation fails closed unless `subprocess.run(...).returncode` is the exact integer `0`.
- `compile.process_returncode` must be an exact integer.
- archived `compile_process.json.process_returncode` must be an exact integer.
- the two evidence return codes must match.
- the matched return code must equal `0`.
- zero-error compiler text and a binary-like EX5 cannot override a non-zero process return code.
- adversarial local gate `V201_METAEDITOR_PROCESS_EXITCODE_AUTHORITY` rejects `1`, `37`, and `-1`, rejects cross-record mismatch, and rejects string/coerced zero evidence.

The local R6 acceptance target is now **57/57 PASS**. This remains source/selftest evidence only; real Owner MetaEditor/MT5 execution is still required before MTF-1 can close.
