# Research Atomic Resume V1

Authority: last successfully committed checkpoint only. A checkpoint contains Factory identity, immutable source contract/hash, pool, tested fingerprints, generation progress, Research Memory and Guided state. The envelope carries a monotonically increasing sequence and SHA-256 of its payload.

Crash semantics: work after the last commit is disposable. On recovery, the system loads the newest valid checkpoint, falls back to the previous commit if the newest is corrupt, validates the immutable source hash, removes only uncommitted `*.tmp` files, and resumes the same Factory.

Pause is cooperative at progress/control boundaries. Force Stop exists only for a worker that cannot reach a control boundary.
