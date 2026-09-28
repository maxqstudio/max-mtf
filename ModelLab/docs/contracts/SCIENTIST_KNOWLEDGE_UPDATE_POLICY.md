# Scientist Knowledge Update Policy — R1

## Purpose

Scientist Chat must understand **what Max already is** before it recommends changes. It may propose ideas outside the current Max contract, but it must not repeatedly suggest capabilities that already exist or confuse current implementation with a future extension.

This policy makes the Scientist knowledge base a **release-governance artifact**, not optional documentation.

## Canonical artifacts

- `ModelLab/scientist/knowledge/SCIENTIST_KNOWLEDGE_BASE.json` — machine-readable Max capability/workflow database consumed by Scientist Chat.
- `ModelLab/docs/contracts/SCIENTIST_KNOWLEDGE_BASE.md` — generated human-readable view of the same database.
- `ModelLab/docs/contracts/MAX_WORKFLOW_CONTRACT_E2E.md` — human-readable end-to-end workflow/authority contract.
- `historical external: WORKFLOW_CONTRACT_AUDIT_R1.json` — machine-readable source audit of critical stage transitions and authority boundaries.
- `ModelLab/scientist/knowledge/scientist_knowledge.py` — generator/loader/source-manifest authority.
- `ModelLab/tests/scientist_knowledge_sync_selftest.py` — release gate.

## Mandatory update rule

Any change to production Python code, `ModelLab/config/config.json`, `ModelLab/config/models/model_registry.json`, or a canonical current contract document changes the Scientist knowledge provenance manifest.

Before a revision may be accepted:

1. update the relevant living docs/contract if semantics changed;
2. run `python scientist_knowledge.py` to regenerate the knowledge database, Markdown view, and E2E audit;
3. run `python scientist_knowledge_sync_selftest.py`;
4. run cumulative acceptance;
5. update `governance/PROJECT_HANDOFF_CURRENT.md` and `governance/CONTRACT_AUDIT_INDEX.md` if authority/revision changed.

If a watched source/document hash differs from the manifest embedded in `ModelLab/scientist/knowledge/SCIENTIST_KNOWLEDGE_BASE.json`, the sync self-test **must FAIL**.

## Scientist recommendation rule

Before proposing a feature/workflow change, Scientist Chat must inspect `max_knowledge` and classify the recommendation:

- **EXISTING** — Max already has it. Do not propose building it again; explain/configure the existing capability.
- **EXTENSION** — core capability exists, but a distinct gap remains. State existing capability first, then the gap.
- **EXPERIMENT** — no new code feature is required; test the idea using existing Factory controls/evidence.
- **NEW** — capability does not exist and may be proposed as new architecture.
- **CONFLICT** — suggestion violates deterministic/governance authority.
- **OUTSIDE_CURRENT_CONTRACT** — scientifically plausible but needs an explicit contract revision before implementation.

Scientist may recommend beyond Max. The restriction is **duplicate ignorance**, not creativity.

## Evidence boundary

The static knowledge base describes capabilities and contracts. It is **not proof** that a live run passed a stage. Current run status comes from committed runtime evidence; current Owner settings and the frozen active research plan remain separate authorities.

Locked/Fresh Forward results remain excluded from same-snapshot tuning even though the knowledge base may explain the Forward contract itself.
