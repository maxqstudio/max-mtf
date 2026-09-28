# Max MTF v2.0.1 — MTF-1 R1 Integrity Repair

## Authority

This repair is a blocker repair for MTF-1. MTF-2 remains **BLOCKED** until this repair passes local acceptance and the Owner MT5 native parity gate is executed separately.

## Repaired defects

### 1. Active release identity

Both canonical active-release records:

- `historical external: Releases/active/release.json`
- `ModelLab/runtime/active_release.json`

must be exact mirrors. The EA path is project-relative (`EA_v2_00/baseline/Max_MTF.mq5`), never a build-container or machine-absolute path. Load-time validation resolves the path inside the current package, recomputes SHA-256, and fails closed on missing artifact, stale SHA, path escape, absolute path, or mirror divergence.

Both records and the frozen inherited-core manifest are explicitly included in the v2.0.1 acceptance tree signature.

### 2. Complete volume parity

M5-derived higher-timeframe parity covers:

- Open
- High
- Low
- Close
- Tick Volume
- Real Volume when available

MT5/broker real volume represented as zero-only is recorded explicitly as `UNAVAILABLE_ZERO_ONLY`. If either the M5 source or native higher-TF reference contains populated real volume, `EXACT_PARITY_REQUIRED` applies and any mismatch fails closed.

### 3. Manifest/data binding and sealed-bundle immutability

`write_bundle()` now:

1. recomputes every frame hash;
2. recomputes alignment hash;
3. recomputes `bundle_identity_sha256` from the supplied manifest core;
4. rejects stale/forged manifest-to-data bindings;
5. rejects an existing destination;
6. acquires an exclusive sibling commit lock;
7. writes to a sibling staging directory;
8. readback-verifies all staged frame/alignment hashes and the manifest identity;
9. atomically renames staging to the final bundle directory;
10. removes staging/lock on failure.

No second write may mutate an existing sealed bundle. Data Quality evidence is embedded into the identity-bound manifest before commit; the builder does not write additional files into the sealed directory after commit.

## Inherited v1.4.5 scientific-core proof

MTF-0/MTF-1 must preserve the inherited scientific core while MTF research remains OFF. `governance/MTF1_INHERITED_V145_SCIENTIFIC_CORE.json` freezes the SHA-256 of the immutable scientific-core files against exact Max single-TF v1.4.5 package SHA-256:

`371a4575ed87a845fb7bdfee4f8ded45fe811a77dcf33c8ed93e9f48ee92c190`

The R1 acceptance verifies that frozen manifest identity and every listed current file hash.

## Acceptance

Required local target: **36/36 PASS**, `first_failed_gate = null`, exact source-tree signature.

New mandatory gates:

- `V201_ACTIVE_RELEASE_IDENTITY`
- `V201_RELEASE_PORTABILITY`
- `V201_REAL_VOLUME_PARITY`
- `V201_MANIFEST_DATA_BINDING`
- `V201_SEALED_BUNDLE_IMMUTABILITY`
- `V201_ATOMIC_BUNDLE_COMMIT`

Real Owner MT5 resampling parity remains an external gate. Local PASS does not promote that external gate to PASS.
