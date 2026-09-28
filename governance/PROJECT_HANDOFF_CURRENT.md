# MAX MTF — Governance Technical Handoff

Human/operator state: [CURRENT_STATE.md](../docs/CURRENT_STATE.md)  
Authority ownership: [SOURCE_AUTHORITY_MAP.md](../docs/SOURCE_AUTHORITY_MAP.md)  
Architecture: [ARCHITECTURE.md](../docs/ARCHITECTURE.md)  
Machine authority: `governance/CURRENT_AUTHORITY.json`, `governance/CURRENT_BASELINE.json`, `governance/EXTERNAL_RUNTIME_GATES.json`.

This file records durable technical governance bindings useful during repair/acceptance work. It is **not** a second current-status authority.

## Canonical ModelLab layout

`ModelLab/` root is operator-only. The authoritative root allowlist and migration ledger are in:

`ModelLab/governance/MODELLAB_LAYOUT_MANIFEST.json`

Implementation authority lives in domain packages. Do not restore root compatibility shims or duplicate active config copies without an explicit contract change.

## Canonical MAX Python binding

Canonical MAX runtime/acceptance authority is Python 3.12 through:
- `ui.ui_bootstrap.ensure_python312()`;
- `ui.ui_launcher.ensure_env()`;
- `ui.ui_launcher.venv_python()`.

PATH Python is bootstrap-only. Scientist Python remains a separate dedicated analytical environment.

## Current acceptance binding

- Current phase: **MTF-1 External Execution Proof**.
- Local acceptance target: **75/75 PASS**.
- Local acceptance authority contains exact ordered 75 gate/script rows.
- This local target is necessary but not sufficient for MTF-1 final closure.

## MTF-1 closure binding

A valid closure uses one shared non-empty `closure_run_id` across:
- fresh complete local acceptance;
- Owner MT5 native execution proof;
- MetaEditor execution proof;
- final closure evidence.

Owner MT5 proof archives actual native M5/M15/H1/H4 inputs/provenance. Verification replays canonical MTF derivation/parity/alignment/DQ/lineage and production verification re-fetches the same live window.

MetaEditor proof binds configured executable identity, exact MQ5 source/deployment, exact command/process record, reparsed compiler log, fresh binary EX5, and the same closure-run identity.

`ModelLab/acceptance/verification/VERIFY_MTF1_FINAL_CLOSURE.cmd` is read-only and may not generate, repair, or overwrite closure evidence.

## Scientific-core bindings

- Strategy geometry handoff is canonical.
- Temporal internal early-stop validation preserves purge/embargo requirements.
- Transformer MoE top-1 routing remains differentiable through selected gate magnitude.
- Router diagnostics are recomputed after best-checkpoint restoration.
- MoE experts are latent learned experts; regime labels are descriptive metadata, not supervised expert identities.
- Deterministic code remains admission/PASS/FAIL authority.

## Scientist Python boundary

Scientist Python is optional analytical support:
- separate interpreter;
- host-authorized inputs;
- capability proxies rather than raw scientific module authority;
- no production mutation;
- no Factory/promotion authority;
- REASONING_ONLY fallback on failure.

Live Owner status must be resolved from exact candidate-bound evidence and reconciled machine-readable governance. See `docs/KNOWN_DEFECTS.md` for the current recorded status conflict.

## Broker symbol authority

The configured symbol is a logical/base identity. Owner MT5 runtime resolves one executable broker symbol:
1. exact case-insensitive match;
2. otherwise one unique prefix/suffix variant;
3. otherwise explicit exact override is required.

Ambiguity fails closed. The resolved broker symbol is propagated through native MTF evidence for that closure run.
