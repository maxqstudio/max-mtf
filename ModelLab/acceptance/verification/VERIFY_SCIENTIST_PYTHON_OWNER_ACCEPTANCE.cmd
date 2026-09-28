@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."
echo ============================================================
echo MAX MTF v2.0.1 - VERIFY EXISTING SCIENTIST PYTHON OWNER EVIDENCE
echo Read-only verification. Does not create or overwrite PASS evidence.
echo ============================================================
where python >nul 2>&1
if not errorlevel 1 goto :run_python

where py >nul 2>&1
if not errorlevel 1 goto :run_py

echo {"status":"FAIL","reason":"CANONICAL_MAX_PYTHON_UNAVAILABLE"}
set "RC=103"
goto :done

:run_python
python -m acceptance.runners.max_python_bootstrap --run-module acceptance.runners.owner_scientist_python_runtime_acceptance -- --verify-existing
set "RC=%ERRORLEVEL%"
goto :done

:run_py
py -m acceptance.runners.max_python_bootstrap --run-module acceptance.runners.owner_scientist_python_runtime_acceptance -- --verify-existing
set "RC=%ERRORLEVEL%"
goto :done

:done
pause
exit /b %RC%
