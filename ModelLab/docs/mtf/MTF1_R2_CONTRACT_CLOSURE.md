# Max MTF v2.0.1 — MTF-1 R2 Contract Closure

## Authority

R2 is a blocker repair for MTF-1. MTF-2 remains **BLOCKED** until this local repair passes and the separate Owner-machine MT5 external gates are executed.

R2 preserves all R1 repairs and adds five mandatory closure contracts.

## 1. Imported M5 continuity is mandatory at seal

An imported M5 source may not rely on M15/H1/H4 aggregate parity as a proxy for exact M5 continuity.

For `source_identity.kind == IMPORTED_M5`:

1. the exact native broker M5 reference for the same terminal/feed/window is required at seal time;
2. `audit_m5_against_native_reference()` is recomputed by the sealing authority;
3. source/reference timestamp sets must be identical;
4. OHLC, tick volume, and real volume semantics must pass exact native-M5 parity;
5. the identity-bound `native_reference_audit` must equal the seal-time recomputation;
6. the native-reference M5 SHA must match the supplied reference bytes.

A missing/extra M5 bar fails even when it is aggregate-neutral and therefore invisible to higher-timeframe parity.

Direct MT5 collection remains the direct native source authority and does not require a second redundant reference fetch.

## 2. Runtime Strategy Registry portability

The packaged baseline Strategy Registry must use project-relative identity:

`EA_v2_00/baseline/Max_MTF.mq5`

Builder/container absolute paths such as `/mnt/data/...` and machine-absolute Windows project paths are forbidden in packaged baseline authority.

## 3. Acceptance runtime immutability

Acceptance is observational. It may not mutate packaged runtime authority.

The cumulative runner hashes these runtime authority files before executing gates and verifies the exact signature after every gate:

- `ModelLab/runtime/active_release.json`
- `ModelLab/runtime/strategy_authority.json`
- `ModelLab/runtime/strategy_challenger_registry.json`

Any mutation terminates acceptance as:

`ACCEPTANCE_RUNTIME_AUTHORITY_MUTATED`

The zero-Champion lifecycle test now initializes registry state only inside a temporary sandbox.

These runtime authorities are also included in the exact-tree acceptance signature where applicable.

## 4. Active-release EA version parity

Active release identity is not only path+SHA. The following must be equal:

`active_release.ea.version == Max_MTF.mq5 #property version == governance/PROJECT_IDENTITY.json ea_version`

A stale or forged version field fails closed.

## 5. Preserved R1 integrity contracts

R2 retains:

- portable active-release path and exact EA SHA;
- exact active-release mirrors;
- real-volume higher-TF parity semantics;
- manifest/data binding;
- sealed bundle immutability;
- staging verification + atomic rename;
- no post-seal Data Quality mutation;
- frozen Max v1.4.5 scientific-core hash proof.

## Acceptance

Required local target: **41/41 PASS**, `first_failed_gate = null`, exact source-tree signature.

New mandatory R2 gates:

- `V201_IMPORTED_M5_CONTINUITY_REQUIRED`
- `V201_IMPORTED_M5_NEUTRAL_BAR_MISSING`
- `V201_RUNTIME_REGISTRY_PORTABILITY`
- `V201_ACCEPTANCE_RUNTIME_IMMUTABILITY`
- `V201_ACTIVE_RELEASE_VERSION_PARITY`

The Owner-machine gates remain external. Local R2 PASS does not promote them to PASS.
