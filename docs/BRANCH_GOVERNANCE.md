# Branch Governance

## Authority

`main` is the accepted/frozen branch.

Only work that has passed the required Control Room audit and any required Owner runtime acceptance may be merged into `main`.

## Work branches

All new build, repair, or phase work must start from the current `main` head and use a separate branch:

- `work/<phase-or-scope>`
- `repair/<scope>` when the work is a narrow corrective repair

Unaccepted work must never be committed directly to `main`.

## Acceptance flow

1. Branch from the current accepted `main`.
2. Implement the scoped change.
3. Run the complete cumulative acceptance required by the project.
4. Produce machine-readable evidence.
5. Control Room audits the exact candidate/tree.
6. Run Owner runtime/external acceptance where required.
7. Only after acceptance, merge the branch to `main`.
8. Update PRD, Roadmap, baseline authority, handoff, and provenance in the same accepted merge when materially affected.

## Accepted-baseline rule

Every accepted merge must preserve exact lineage using at least:

- semantic version;
- source tree signature;
- suite signature;
- artifact SHA256 where a packaged candidate exists;
- build scope / build ID;
- cumulative acceptance result;
- relevant Owner runtime/external evidence status.

## Rejected / unfinished work

Rejected or unfinished work remains on its work branch. It must not change the accepted authority on `main`.

## Prompts

Builder/repair prompts are chat/control artifacts and are not committed as canonical project documentation.
