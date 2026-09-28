# MAX MTF

Public source authority for the MAX MTF quantitative research and MetaTrader 5 stack.

Current development state:
- MTF-1 data authority: historically closed.
- MTF-2 feature/label contract: implemented and source-tested.
- MTF-3 exact timestamp purge authority: implemented and source-tested.
- MTF-4 deterministic Strategy Challenger: implementation in progress; V204 is the current source-level gate.
- MTF-5+ model research, ONNX, shadow deployment, and promotion: not proven.

Active EA source: EA_v2_00/baseline/Max_MTF.mq5.

This repository is source-only. Owner runtime evidence, broker provenance, market data, screenshots, logs, compiled MetaTrader output, model binaries, and machine calibration are excluded. See PUBLIC_SOURCE_POLICY.md.

Development and source testing run on GitHub Actions using Windows runners. Environment-dependent MT5/MetaEditor acceptance is performed by the Owner only at the end of a phase.

Read first: PROJECT_PROFILE.yaml, docs/SYSTEM_OVERVIEW.md, docs/CURRENT_STATE.md, docs/PROJECT_MANIFEST.md, docs/SOURCE_AUTHORITY_MAP.md, docs/ARCHITECTURE.md, docs/WORKFLOW_STATE_MACHINE.md, docs/TEST_ACCEPTANCE_MATRIX.md, docs/PROJECT_TRUTH_SYNC.md, docs/SEQUENCE_CONTRACTS.md.

Evidence rule:
- source tests prove source behavior only;
- GitHub Actions proves the exact Git candidate and CI suite;
- Owner MT5/MetaEditor evidence proves environment-dependent runtime behavior;
- no Challenger becomes Champion automatically.
