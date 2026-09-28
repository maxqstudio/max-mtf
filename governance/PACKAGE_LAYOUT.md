# Max MTF v2.0.1 Package Layout
Active scientific/runtime source layout is preserved; the current MTF-1 phase adds closure execution-proof authorities without revision-number identity.

- `EA_v2_00/baseline` — canonical active EA copy.
- `EA_v2_00/challengers`, `EA_v2_00/archive` — Strategy lifecycle.
- `Models/baseline`, `Models/challengers`, `Models/archive` — Model lifecycle.
- `Releases/active`, `Releases/challengers`, `Releases/archive` — release lifecycle.
- `Data/MTF/native`, `Data/MTF/bundles` — MTF-1 data authority.
- `EA_v1_06` — inherited single-TF reference only; never active Max MTF authority.

The active release remains `BASELINE-MTF-V2`; Strategy Champion and Model Champion remain null.

## Canonical ModelLab domain layout

`ModelLab/` is an operator surface, not an implementation dump. Its only direct files are:

- `ModelLab/START_UI.cmd`
- `ModelLab/RUN_ACCEPTANCE.cmd`
- `ModelLab/RUN_CUDA_ACCEPTANCE.cmd`
- `ModelLab/RUN_LANGGRAPH_ACCEPTANCE.cmd`
- `ModelLab/RUN_MTF1_ACCEPTANCE.cmd`
- `ModelLab/RUN_MTF1_OWNER_ACCEPTANCE.cmd`
- `ModelLab/RUN_MTF1_METAEDITOR_ACCEPTANCE.cmd`
- `ModelLab/RUN_MTF1_FINAL_CLOSURE.cmd`
- `ModelLab/RUN_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd`

Implementation authority lives below the canonical domain folders: `acceptance/`, `config/`, `core/`, `data/`, `factory/`, `host/`, `models/`, `mtf/`, `research/`, `scientist/`, `strategy/`, `tools/`, `requirements/`, `ui/`, plus retained evidence/docs/governance/runtime/skills/tests/max_graph folders. The one authoritative root allowlist and the complete 151-entry relocation ledger are `ModelLab/governance/MODELLAB_LAYOUT_MANIFEST.json`. Historical/runtime evidence formerly present at root is archived below `evidence/` and is not current authority.


## MTF-1 closure run authority

- Run identity: `historical external: owner_acceptance/runtime/MTF1_CLOSURE_RUN.json`.
- One-click full runner: `ModelLab/RUN_MTF1_FINAL_CLOSURE.cmd`.
- Read-only final verifier: `ModelLab/acceptance/verification/VERIFY_MTF1_FINAL_CLOSURE.cmd`.
- Final evidence: `historical external: owner_acceptance/evidence/mtf1/OWNER_MTF1_FINAL_CLOSURE.json`.

## Owner MT5 runtime proof

- Runner: `ModelLab/RUN_MTF1_OWNER_ACCEPTANCE.cmd`.
- Config: `historical external: owner_acceptance/runtime/OWNER_MTF1_RUNTIME_ACCEPTANCE_CONFIG.json`.
- Summary evidence: `historical external: owner_acceptance/evidence/mtf1/OWNER_MTF1_RUNTIME_ACCEPTANCE.json`.
- Run-specific raw input archive: `owner_acceptance/evidence/mtf1/owner_runtime/<closure_run_id>/`.
- Verifier: `ModelLab/acceptance/verification/VERIFY_MTF1_OWNER_ACCEPTANCE.cmd`.

The archive contains the actual native M5/M15/H1/H4 inputs and MT5 provenance used by the execution. Production verification reloads/recomputes from the archive and live-revalidates the exact Owner MT5 window.

## MetaEditor execution proof

- Runner: `ModelLab/RUN_MTF1_METAEDITOR_ACCEPTANCE.cmd`.
- Config: `historical external: owner_acceptance/runtime/OWNER_MTF1_METAEDITOR_ACCEPTANCE_CONFIG.json`.
- Summary evidence: `historical external: owner_acceptance/evidence/mtf1/OWNER_MTF1_METAEDITOR_ACCEPTANCE.json`.
- Run-specific compile archive: `owner_acceptance/evidence/mtf1/metaeditor/<closure_run_id>/`.
- Verifier: `ModelLab/acceptance/verification/VERIFY_MTF1_METAEDITOR_ACCEPTANCE.cmd`.

The archive binds the current configured MetaEditor executable identity, exact deployed MQ5, command argv, compiler log, process record, and generated EX5. The verifier reparses the archived compiler log and validates current tool/source identity rather than trusting caller summary fields.

## MTF-1 closure rule

Fresh local **75/75 PASS** + Owner MT5 archived replay and live revalidation PASS + MetaEditor current-tool/reparsed-zero-error-log/fresh-EX5 proof PASS with exact signed process-returncode binding retained as diagnostic evidence + one shared `closure_run_id` = `MTF_1_CLOSED`.

`ModelLab/acceptance/verification/VERIFY_MTF1_FINAL_CLOSURE.cmd` is observational/read-only and must never regenerate final evidence.

Final closure bootstrap authority: `ModelLab/RUN_MTF1_FINAL_CLOSURE.cmd` resolves/repairs the canonical MAX Python 3.12 venv, verifies pinned Torch capability, and launches every closure stage with that one interpreter.

## Scientist Python analytical runtime

- Shared host executor: `ModelLab/scientist/python/scientist_python_runtime.py`.
- Governed capability surface: `ModelLab/scientist/python/scientist_python_capabilities.py`.
- Dedicated child: `ModelLab/scientist/python/scientist_python_child.py`.
- Generated scientific imports resolve to capability proxies rather than raw third-party modules; transitive ctypes/native filesystem/process/network authority is denied.
- Dedicated Owner environment remains separate from canonical MAX Python and failures fall back to `REASONING_ONLY`.
- Canonical one-click Owner acceptance: `ModelLab/RUN_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd`.
- Canonical live verifier: `ModelLab/acceptance/runners/owner_scientist_python_runtime_acceptance.py`; read-only verify helper: `ModelLab/acceptance/verification/VERIFY_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd`.
- Live evidence: `historical external: owner_acceptance/evidence/scientist_python/OWNER_SCIENTIST_PYTHON_RUNTIME_ACCEPTANCE.json` (runtime evidence, excluded from source-signature authority).
- This capability is analytical support only; MTF-2 remains blocked.

## Canonical MAX Python authority

`ModelLab/RUN_ACCEPTANCE.cmd` and `ModelLab/RUN_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd` use PATH Python/`py` only to enter `acceptance.runners.max_python_bootstrap`. That bootstrap reuses `ui.ui_bootstrap.ensure_python312()` and `ui.ui_launcher.ensure_env()/venv_python()` to resolve one supported Python 3.12 canonical MAX venv. All MAX-side Owner Scientist acceptance stages then run under that exact interpreter; evidence separately records bootstrap Python and canonical MAX Python. Legacy `ModelLab/.venv` is not authority. The dedicated Scientist Python venv remains separate.
