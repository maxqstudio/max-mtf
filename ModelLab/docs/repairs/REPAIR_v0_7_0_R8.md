# CPMF v0.7.0 R8 — Windows Factory Job I/O Repair

## Root cause
R7 allowed more than one process to rewrite the same `historical external: factory_runs/_jobs/<job>.json` and used a fixed `.tmp` path. On Windows, concurrent replacement or a transient file lock can raise `PermissionError: [WinError 5] Access is denied` at `os.replace`. This is telemetry/control-plane failure, not a candidate/model failure.

## Repair
- Worker owns the authoritative job JSON after process spawn. UI/navigation is read-only.
- `STOP RESEARCH` uses an out-of-band `.stop` sentinel; the UI no longer rewrites job JSON.
- Parent writes the initial QUEUED record before spawn and does not race the worker by rewriting RUNNING state afterward.
- Atomic JSON writes use unique same-directory temp files plus bounded Windows retry/backoff for transient WinError 5/32.
- Candidate leaderboard JSON uses the same hardened atomic writer.
- Legacy settings/API persistence is unchanged.

## Acceptance
`FACTORY_JOB_IO_WINDOWS_LOCK` simulates repeated PermissionError on atomic replace, proves retry succeeds, proves STOP does not mutate the job JSON, and proves the parent does not write job state after spawning the worker.
