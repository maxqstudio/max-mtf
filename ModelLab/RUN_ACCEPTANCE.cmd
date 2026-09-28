@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Max MTF v2.0.1 MTF-1 Acceptance

REM PATH Python/py is bootstrap-only. Canonical MAX runtime authority is resolved by
REM ui.ui_bootstrap + ui.ui_launcher and all acceptance executes in that exact venv.
where python >nul 2>&1
if not errorlevel 1 (
  python -m acceptance.runners.max_python_bootstrap --run-module acceptance.runners.run_acceptance
  set "RC=%ERRORLEVEL%"
  goto :done
)
where py >nul 2>&1
if not errorlevel 1 (
  py -m acceptance.runners.max_python_bootstrap --run-module acceptance.runners.run_acceptance
  set "RC=%ERRORLEVEL%"
  goto :done
)

echo {"status":"FAIL","reason":"CANONICAL_MAX_PYTHON_UNAVAILABLE","detail":"No bootstrap Python/launcher is available to resolve supported Python 3.12."}
set "RC=103"

:done
pause
exit /b %RC%
