# MAX MTF — Read First

**Max MTF v2.0.1 — MTF-1 External Execution Proof**

Current local acceptance target: **75/75 PASS** with `first_failed_gate=null`. Local PASS is necessary but does not substitute for required Owner/external runtime evidence.

The cumulative runner owns the exact ordered **75 `(gate, script)` pairs**.

```text
BUILD ACCEPTANCE : PASS
GATES            : 75 / 75
first_failed_gate: null
execution_mode   : FRESH_FULL
```

Do not reconstruct this project from chat history or scan the entire repository first.

Read in this order:

1. [PROJECT_PROFILE.yaml](PROJECT_PROFILE.yaml)
2. [SYSTEM_OVERVIEW.md](docs/SYSTEM_OVERVIEW.md)
3. [CURRENT_STATE.md](docs/CURRENT_STATE.md)
4. [PROJECT_MANIFEST.md](docs/PROJECT_MANIFEST.md)
5. [SOURCE_AUTHORITY_MAP.md](docs/SOURCE_AUTHORITY_MAP.md)
6. [ARCHITECTURE.md](docs/ARCHITECTURE.md)
7. [WORKFLOW_STATE_MACHINE.md](docs/WORKFLOW_STATE_MACHINE.md)
8. [MODULE_MAP.md](docs/MODULE_MAP.md)
9. [FLOW_INDEX.md](docs/FLOW_INDEX.md)
10. [SYMBOL_INDEX.md](docs/SYMBOL_INDEX.md)
11. [TEST_ACCEPTANCE_MATRIX.md](docs/TEST_ACCEPTANCE_MATRIX.md)
12. [DOC_SYNC_MATRIX.md](docs/DOC_SYNC_MATRIX.md)
13. [PROJECT_TRUTH_SYNC.md](docs/PROJECT_TRUTH_SYNC.md)
14. exact relevant source ranges and tests.

For operations use [RUNBOOK.md](docs/RUNBOOK.md). For product intent use [docs/PRD_CURRENT.md](docs/PRD_CURRENT.md) and [docs/ROADMAP_CURRENT.md](docs/ROADMAP_CURRENT.md).

Machine-readable authority remains under `governance/`, `ModelLab/governance/`, and `ModelLab/runtime/`.

## Operator entry points

From `ModelLab/`:

- `ModelLab/START_UI.cmd` — Control Room.
- `ModelLab/RUN_ACCEPTANCE.cmd` — local cumulative acceptance.
- `ModelLab/RUN_MTF1_FINAL_CLOSURE.cmd` — complete MTF-1 closure workflow on the required Owner environment.
- `ModelLab/RUN_MTF1_OWNER_ACCEPTANCE.cmd` — Owner MT5 evidence.
- `ModelLab/RUN_MTF1_METAEDITOR_ACCEPTANCE.cmd` — MetaEditor evidence.
- `ModelLab/RUN_SCIENTIST_PYTHON_OWNER_ACCEPTANCE.cmd` — Scientist Python Owner runtime acceptance.

Runner existence is not PASS evidence.
