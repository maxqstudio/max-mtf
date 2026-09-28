# REPAIR v0.5.4 — Windows Python 3.12 bootstrap

## Root cause
`ModelLab/START_UI.cmd` v0.5.3 checked `%errorlevel%` inside parenthesized CMD blocks. `%errorlevel%` is expanded when the block is parsed, so a failed `py -3.12` probe could still branch to `:run_py`. The launcher then printed `Menggunakan Python 3.12` even though no 3.12 runtime existed, after which `py -3.12` exited with code 103.

## Repair
- Removed Python-version discovery logic from nested batch blocks.
- Added `ModelLab/ui/ui_bootstrap.py`, intentionally compatible with the user's existing Python (including 3.14).
- Discovers a concrete Python 3.12 executable via direct aliases, `py -3.12`, Windows registry, and standard install paths.
- If absent, tries Python Install Manager, legacy launcher auto-install (`PYLAUNCHER_ALLOW_INSTALL=1`), then WinGet.
- After discovery/install it invokes the concrete `python.exe` path, not `py -3.12`, preventing launcher/runtime disagreement.
- Writes `bootstrap.log` for actionable diagnostics.
- Python 3.14 or any other system Python is never removed or modified.

All v0.5.3 research, adaptive Supervisor, LLM Scientist, ONNX preflight/export fixes, locked-test policy, and Champion governance remain unchanged.

Additional hardening: `ModelLab/START_UI.cmd` uses label-based flow with no `%errorlevel%` reads inside parenthesized blocks, so CMD parse-time expansion cannot misreport bootstrap success.
