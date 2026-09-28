# REPAIR v0.5.6 — Windows path-length containment

Root cause of the v0.5.4 install failure was WinError 206 while pip installed ONNX into a deeply nested project-local `.venv`. The package was being extracted into repeated long folder names, then ONNX added long backend-test paths.

v0.5.6 changes environment placement, not research logic:

- virtual environment is no longer stored under the project folder;
- preferred Windows location is `<project-drive>:\\.cpml\venv312`, with `%LOCALAPPDATA%\CPML\venv312` fallback;
- pip TEMP/TMP/cache also use the same short environment root;
- legacy project `.venv` is ignored and best-effort removed;
- package internal folders are shortened to `CPMF_v0_5_6\ModelLab`;
- base requirements and Streamlit requirements install separately, removing nested `-r` path dependence;
- Python 3.12 bootstrap, Adaptive Supervisor, LLM Scientist, ONNX preflight and governance are otherwise unchanged.
