# CPMF v0.7.5 R3 Hotfix1 — Abort Terminal Lifecycle

## Defect
Sidebar ABORT called `force_stop()`. A successful force stop committed `STOPPED`, and `STOPPED` is intentionally resumable. Therefore the next UI rerun again rendered `RESUME | ABORT` instead of `START RESEARCH`.

## Repair
- Added explicit `abort_job()` lifecycle authority.
- Successful ABORT commits `ABORTED`, which is terminal and not resumable.
- `STOPPED` remains resumable; STOP behavior is unchanged.
- Sidebar ABORT now calls `abort_job()`.
- After ABORT, a new research job can be started immediately.
- Added cumulative acceptance gate `R11_ABORT_TERMINAL_LIFECYCLE`.
