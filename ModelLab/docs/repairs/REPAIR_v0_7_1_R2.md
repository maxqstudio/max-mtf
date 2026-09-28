# CPMF v0.7.1 R2 — Atomic Research Resume Repair

## Root cause
A Windows/device restart killed the background worker while the persisted job remained STOP_REQUESTED/RUNNING. Cooperative STOP could also wait indefinitely inside a native fit/CPCV unit. v0.7.1 had no durable resume authority for an in-flight Discovery Factory.

## Repair
- Job lifecycle: RUNNING → PAUSE_REQUESTED → PAUSED → RESUME; dead active worker → INTERRUPTED → RESUME.
- Cooperative STOP plus FORCE STOP fallback.
- Out-of-band pause/stop sentinels preserve single-writer job JSON discipline.
- Checksummed atomic Discovery checkpoints with previous-commit backup.
- Commit boundaries: snapshot/preflight, Supervisor generation, each CPCV candidate, Guided/Research Memory generation.
- Resume validates immutable Discovery snapshot SHA-256.
- Partial temp files are discarded; uncommitted unit is replayed, committed units are retained.
- Legacy v0.7.1 Factory recovery bootstraps from existing completed generation evidence.

## Governance
Resume never changes KPI, model contract, research source, compute backend authority, Monte Carlo settings, or Global Research Memory rules.
