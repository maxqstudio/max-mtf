# MAX MTF — Current Accepted Baseline

Canonical version: **MAX MTF v2.0.1**

This document records the accepted **source/artifact baseline**. External runtime proof is listed separately and must not be inferred from source acceptance.

## Accepted artifact identity

- Candidate ZIP SHA256: `6ce067da5cb22d7809905df2743d242fd291b0c643e8df81228c8be767cbe164`
- Candidate size: `4,235,610 bytes`
- Source tree signature: `4e34f7202aa4137d660c953be2fa57d16898e1052ca3790990dc8e7637907b3f`
- Suite signature: `1a29b4c5db502a49fbc4ecefbde8772f400ac836b051505ce1c4c44f6246f1c1`
- Build scope: `MAX_MTF_V2_0_1_OWNER_ACCEPTANCE_POSTSEAL_EVIDENCE_AND_EXITCODE_REPAIR`
- Build ID: `V201_4E34F7202AA4_1A29B4C5`
- Local cumulative acceptance: **75/75 PASS / FRESH_FULL**

## GitHub source baseline

The accepted package source is mirrored on `main`.

- Accepted source HEAD at this documentation snapshot: `3e969efcdeb4ca6a2ae63acbd80592e378d2a446`
- Package mirror commit recorded by baseline authority: `08bb7a9207614d30457ccd1c65dc9ac084494b54`
- Package paths checked: `939`
- Missing paths: `0`
- Byte mismatches: `0`

The packaged ZIP remains identified by the SHA256 above and Drive file ID `1fiR6yGpTUfFFjauLrnKw87lLf7yCMmM7`.

GitHub is the accepted source-code baseline authority; the ZIP SHA remains the packaged-artifact identity.

## Release/lifecycle baseline

```text
active release      = BASELINE-MTF-V2
baseline status     = BASELINE_NOT_CHAMPION
strategy champion   = null
model champion      = null
deployed_mt5        = null
```

The current Strategy execution authority is a baseline configuration and explicitly records `champion: false`.

## Local acceptance authority

Committed report:

`historical external: ModelLab/evidence/current/BUILD_ACCEPTANCE_v2_0_1.json`

Recorded result:
- gate count: 75;
- status: PASS;
- `first_failed_gate=null`;
- `execution_mode=FRESH_FULL`.

This proves the bound local cumulative suite. It does not prove external runtime gates.

## External runtime / Owner evidence

MTF-1 is **not closed** in this source snapshot.

The external-gate registry still requires real Owner-machine evidence for relevant MT5/MetaEditor/runtime paths. The final production MTF-1 summary files named by the closure contract are not committed in this GitHub snapshot.

Required MTF-1 closure summaries:
- `historical external: owner_acceptance/evidence/mtf1/OWNER_MTF1_RUNTIME_ACCEPTANCE.json`
- `historical external: owner_acceptance/evidence/mtf1/OWNER_MTF1_METAEDITOR_ACCEPTANCE.json`
- `historical external: owner_acceptance/evidence/mtf1/OWNER_MTF1_FINAL_CLOSURE.json`

Existing `test_owner_*` directories are test/fixture evidence and are not substitutes for a production closure run.

### Scientist Python status reconciliation

Some historical/current narrative text has described the Scientist Python Owner Windows runtime as `READY / PASS`. At this snapshot, `governance/CURRENT_AUTHORITY.json` still contains a pending Owner-runtime substatus and the named final Scientist Owner evidence file is not committed.

Therefore the GitHub source baseline alone does not independently prove that external Scientist Owner runtime state. Treat the designated live Owner evidence as the authority when reconciling that status.

## Phase authority

| Phase | Status |
|---|---|
| MTF-0 | foundation established |
| MTF-1 | source/data implementation accepted; final external closure pending |
| MTF-2 | BLOCKED pending MTF-1 closure |
| MTF-3+ | blocked/planned by roadmap dependency |

## Repository rule

`main` is accepted/frozen only.

Every new build, repair, or documentation change starts from current `main` on a dedicated work branch. Do not mutate accepted authority on `main` before the scoped work passes its required acceptance.

For architecture and ownership, see [ARCHITECTURE.md](ARCHITECTURE.md).
