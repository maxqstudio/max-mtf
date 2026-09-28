# DOCUMENTATION INDEX

Authority source snapshot: `main@3e969efcdeb4ca6a2ae63acbd80592e378d2a446`

The documentation is organized using the project handoff/codebase-orientation workflow. Source and runtime evidence remain stronger than narrative documentation.

## Core handoff pack

| Read order | Document | Responsibility |
|---:|---|---|
| 1 | [PROJECT_PROFILE.yaml](../PROJECT_PROFILE.yaml) | machine-readable governance profile and contract applicability |
| 2 | [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) | human-first mental model and Human Comprehension Gate |
| 3 | [CURRENT_STATE.md](CURRENT_STATE.md) | short live status, proven/not-proven, blockers, next legal action |
| 4 | [PROJECT_MANIFEST.md](PROJECT_MANIFEST.md) | project identity, repositories, authorities, entry points, constraints |
| 5 | [SOURCE_AUTHORITY_MAP.md](SOURCE_AUTHORITY_MAP.md) | canonical authority for each concern and recorded conflicts |
| 6 | [ARCHITECTURE.md](ARCHITECTURE.md) | components, boundaries, processes, persistence, trust model |
| 7 | [WORKFLOW_STATE_MACHINE.md](WORKFLOW_STATE_MACHINE.md) | legal lifecycle states/transitions, failure and rollback behavior |
| 8 | [MODULE_MAP.md](MODULE_MAP.md) | file-level navigation |
| 9 | [FLOW_INDEX.md](FLOW_INDEX.md) | end-to-end call chains and side effects |
| 10 | [SYMBOL_INDEX.md](SYMBOL_INDEX.md) | authority-bearing symbols and line hints bound to exact SHA |
| 11 | [TEST_ACCEPTANCE_MATRIX.md](TEST_ACCEPTANCE_MATRIX.md) | requirement-to-evidence map and evidence boundary |
| 12 | [DOC_SYNC_MATRIX.md](DOC_SYNC_MATRIX.md) | transactional source↔documentation impact rules |
| 13 | [PROJECT_TRUTH_SYNC.md](PROJECT_TRUTH_SYNC.md) | critical claim ↔ source ↔ test ↔ runtime traceability |

## Supporting current documents

| Document | Role |
|---|---|
| [RUNBOOK.md](RUNBOOK.md) | exact operator/start/test/closure/recovery workflow |
| [KNOWN_DEFECTS.md](KNOWN_DEFECTS.md) | confirmed defects/authority conflicts |
| [UI_INFORMATION_ARCHITECTURE.md](UI_INFORMATION_ARCHITECTURE.md) | UI page → backend authority mapping |
| [BASELINE_CURRENT.md](BASELINE_CURRENT.md) | accepted package/source baseline detail |
| [PRD_CURRENT.md](PRD_CURRENT.md) | product/scientific requirements |
| [ROADMAP_CURRENT.md](ROADMAP_CURRENT.md) | future MTF phase order/dependencies |
| [BRANCH_GOVERNANCE.md](BRANCH_GOVERNANCE.md) | branch/acceptance/merge policy |
| [DATA_CONTRACTS.md](DATA_CONTRACTS.md) | authority-bearing research/MTF data semantics |
| [DECISIONS.md](DECISIONS.md) | durable documentation/governance decisions |
| [HANDOFF_CURRENT.md](HANDOFF_CURRENT.md) | compatibility pointer to CURRENT_STATE; not a separate status authority |

## Machine-readable authorities

- `governance/PROJECT_IDENTITY.json`
- `governance/CURRENT_AUTHORITY.json`
- `governance/CURRENT_BASELINE.json`
- `governance/EXTERNAL_RUNTIME_GATES.json`
- `ModelLab/governance/MODELLAB_LAYOUT_MANIFEST.json`
- `ModelLab/governance/MODEL_TRAINING_METHOD_CONTRACT_V1.json`
- `ModelLab/runtime/active_release.json`
- `ModelLab/runtime/strategy_authority.json`
- Strategy/Model Challenger and Champion registries.

When two current authorities conflict, record the conflict in [SOURCE_AUTHORITY_MAP.md](SOURCE_AUTHORITY_MAP.md), [PROJECT_TRUTH_SYNC.md](PROJECT_TRUTH_SYNC.md), and [KNOWN_DEFECTS.md](KNOWN_DEFECTS.md); do not resolve by assumption.

## Historical material

Historical repairs, old handoffs, prior evidence, older MTF closure notes, and `EA_v1_06/` explain lineage only. They cannot override current source/runtime authority.

## Update rules

- Human/domain mental-model semantic change → update `.workflow` semantic specs, then regenerate SYSTEM_OVERVIEW.
- State/status change → update `.workflow` state/acceptance specs, then regenerate CURRENT_STATE and TEST_ACCEPTANCE_MATRIX.
- Authority ownership/conflict change → update `.workflow/authority.json`, then regenerate SOURCE_AUTHORITY_MAP.
- Workflow transition change → update `historical external: .workflow/workflows/*.json`, then regenerate WORKFLOW_STATE_MACHINE and FLOW_INDEX.
- Module/symbol move → regenerate compiler code facts and MODULE_MAP/SYMBOL_INDEX.
- Operator command/recovery change → update `.workflow/contracts.json`, then regenerate RUNBOOK.
- Product requirement/phase plan change → update PRD/ROADMAP.
- Never duplicate the same volatile status across several narrative files.
