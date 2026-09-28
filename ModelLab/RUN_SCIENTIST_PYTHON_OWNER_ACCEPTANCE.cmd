@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title MAX MTF v2.0.1 - Scientist Python Owner Acceptance

echo ============================================================
echo MAX MTF v2.0.1 - SCIENTIST PYTHON OWNER WINDOWS ACCEPTANCE
echo Canonical MAX Python 3.12/venv ^> Scientist setup/health ^> fresh 75 gates ^> live runtime ^> verify
echo MTF-2 remains BLOCKED.
echo ============================================================

REM PATH Python/py is bootstrap-only. The Python bootstrap resolves Python 3.12,
REM ensures the existing canonical MAX venv, and launches the entire Owner workflow
REM under that one immutable interpreter identity. Label-based control flow preserves
REM the exact child return code without parenthesized %%ERRORLEVEL%% expansion hazards.
where python >nul 2>&1
if not errorlevel 1 goto :run_python

where py >nul 2>&1
if not errorlevel 1 goto :run_py

echo {"status":"FAIL","reason":"CANONICAL_MAX_PYTHON_UNAVAILABLE","detail":"No bootstrap Python/launcher is available to resolve supported Python 3.12."}
set "RC=103"
goto :done

:run_python
python -m acceptance.runners.max_python_bootstrap --run-module acceptance.runners.owner_scientist_python_runtime_acceptance -- --one-click
set "RC=%ERRORLEVEL%"
goto :done

:run_py
py -m acceptance.runners.max_python_bootstrap --run-module acceptance.runners.owner_scientist_python_runtime_acceptance -- --one-click
set "RC=%ERRORLEVEL%"
goto :done

:done
echo ============================================================
if "%RC%"=="0" (
  echo SCIENTIST PYTHON OWNER ACCEPTANCE: PASS
) else (
  echo SCIENTIST PYTHON OWNER ACCEPTANCE: FAIL
  echo See owner_acceptance\evidence\scientist_python\OWNER_SCIENTIST_PYTHON_RUNTIME_ACCEPTANCE.json
)
echo ============================================================
pause
exit /b %RC%
