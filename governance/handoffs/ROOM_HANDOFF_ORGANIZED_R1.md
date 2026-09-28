# Max Research Agent — Package Organization R1

- Stage 1–11: **CLOSED**
- Stage 12: **NOT STARTED**
- Package layout: **ORGANIZED R1 CLOSED**
- Fresh cumulative: **97/97 PASS**
- `first_failed_gate`: `None`
- Source tree: `7193c27932a18539a9ac0486e39bcf85cfaa4880affacd18dc0f746ac44e06ca`
- Suite: `bd228572dda2dbbab657e7e16af976acc31e40026f454556b983419cc0a306d6`

## Layout

- `README_FIRST.md` — package entrypoint
- `ModelLab/` — production runtime source + minimal runtime state
- `ModelLab/tests/` — self-tests/stage gates
- `ModelLab/docs/` — contracts/research/UI/repairs/reference
- `ModelLab/evidence/` — current/history/UI/research evidence
- `governance/` — authority/checkpoints/seals/handoffs
- `owner_acceptance/` — Owner runtime/UI evidence
- `history/` — superseded room handoffs/root repairs
- `migration_tools/` — lineage migration scripts
- `EA_v1_06/` — MQL5 assets

Scientific KPI/workflow/topology authority is unchanged. Scientist Chat Clear Hotfix1 is preserved.
