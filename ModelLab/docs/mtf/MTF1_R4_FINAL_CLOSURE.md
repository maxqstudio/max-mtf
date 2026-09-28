# Max MTF v2.0.1 — MTF-1 R4 Final Closure + v1.4.6 Bugfix Rebase

## Scope

Governance/evidence closure only. MTF-2 remains blocked. KPI, CPCV, evaluator, model bounds, strategy authority, promotion flow and MTF-2 functionality are not changed.

## Repairs

### External requirement lock

The canonical registry remains `governance/EXTERNAL_RUNTIME_GATES.json`, while acceptance enforces these non-negotiable MTF-1 phase invariants:

- `OWNER_MT5_NATIVE_MTF_RESAMPLING_PARITY = REQUIRED_ON_OWNER_MACHINE`
- `OWNER_MT5_TERMINAL_DATA_ROOT_DETECTION = REQUIRED_ON_OWNER_MACHINE`
- `METAEDITOR_MAX_MTF_V2_COMPILE = REQUIRED_ON_OWNER_MACHINE`
- `MTF_STRATEGY_RUNTIME = NOT_APPLICABLE_MTF1`

Editing the registry and syncing Package Manifest cannot downgrade these obligations without failing acceptance.

### Exact-candidate Owner evidence

Owner runtime execution is refused unless the exact current tree already has local acceptance PASS. Runtime evidence records and the verifier re-checks:

- source-tree signature;
- suite signature;
- local acceptance SHA-256;
- external runtime registry SHA-256;
- active EA project-relative path;
- active EA SHA-256;
- active EA version;
- Owner runtime config SHA-256.

Owner config is runtime input, not source-tree authority; its SHA is separately bound to evidence.

### Scientist v1.4.6 bugfix rebase

`_extract_json_with_bounded_format_repair()` is the shared response recovery authority for Discovery proposal, Policy Review, Research Director and Stage Review. A malformed provider-success response may receive one serializer-only retry at temperature `0`. No semantic changes are authorized. The repaired response passes the same parser and downstream deterministic schema/bounds cleaning. A second malformed response fails closed.

## Local closure target

**48/48 PASS**, `first_failed_gate=null`, exact tree and suite signatures. Local closure does not replace Owner MT5 or MetaEditor runtime proof.
