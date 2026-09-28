# Stage 11 — Release & Authority Integrity Repair

## Scope
Governance/release integrity only. Scientific KPI, model topology, Data→Champion lifecycle, AUTO/MANUAL authority, LLM Scientist, and Scientist Chat runtime contracts are unchanged.

## Confirmed defects from sealed R5
1. `governance/PACKAGE_MANIFEST.json` was stale at Stage 1–7 / 93-of-93 and still pointed to Stage 8 although R5 authority was Stage 1–10 / 96-of-96.
2. `RELEASE_SYNC` did not cross-check package manifest/current authority/R5 checkpoint state, so stale package authority could coexist with a green cumulative suite.
3. `governance/PACKAGE_MANIFEST.json` did not participate in the acceptance source-tree signature or Scientist Knowledge provenance.
4. R5 `governance/checkpoints/CHECKPOINT_FILE_SHA256.json` contained 20 stale hashes after later Stage 10 closure changes; the seal flow generated per-file hashes too early and never verified them after final acceptance.

## Repair
- Added `STAGE11_RELEASE_AUTHORITY_INTEGRITY` as cumulative gate 97.
- Added cross-authority package metadata checks to `ModelLab/tests/release_sync_selftest.py`.
- Bound `governance/PACKAGE_MANIFEST.json` into exact-tree acceptance hashing.
- Added `governance/PACKAGE_MANIFEST.json` and `README_FIRST.md` to Scientist Knowledge watched authority.
- Added `ModelLab/core/checkpoint_integrity.py` V2 with deterministic generate/verify, missing/extra/hash mismatch detection, and post-acceptance sealing order.
- Kept R5 `governance/checkpoints/CHECKPOINT_PRE_STAGE11_STATUS.json` immutable as historical baseline evidence.
- External NOT_RUN gates remain NOT_RUN and cannot be promoted by package metadata.

## Closure rule
Dedicated Stage11 + targeted regressions → Scientist Knowledge/workflow PASS → fresh 97/97 → canonical CLOSED update → final fresh 97/97 → create PRE-Stage12 status/handoff → generate+verify `governance/checkpoints/CHECKPOINT_FILE_SHA256.json` V2 → ZIP readback/hash → R6 seal.
