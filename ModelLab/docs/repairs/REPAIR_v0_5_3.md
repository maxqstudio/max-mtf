# v0.5.4 Python Runtime Bootstrap Repair

## Defect
`ModelLab/START_UI.cmd` used `py -3`, which selected the newest installed Python (3.14.6 on the reported machine). `ModelLab/ui/ui_launcher.py` correctly rejected that interpreter because the pinned ONNX/converter stack is validated on Python 3.12, so the UI never started.

## Repair
- `ModelLab/START_UI.cmd` explicitly selects Python 3.12.
- If Python 3.12 is absent, it first uses the official Python Install Manager (`pymanager install 3.12`) when available.
- Legacy systems fall back to a per-user WinGet Python 3.12 install.
- Existing Python 3.14 is not removed, downgraded, or made unusable.
- `.venv` runtime version is inspected; stale/incompatible environments are rebuilt automatically.
- `ModelLab/tools/maintenance/RESET_ENV.cmd` only removes the project-local `.venv`.

## Canonical runtime
Python 3.12 for this Model Lab revision.
