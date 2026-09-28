@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."
where python >nul 2>&1
if not errorlevel 1 (
  python -m acceptance.runners.max_python_bootstrap --run-module scientist.python.scientist_python_setup -- setup
  exit /b %ERRORLEVEL%
)
where py >nul 2>&1
if not errorlevel 1 (
  py -m acceptance.runners.max_python_bootstrap --run-module scientist.python.scientist_python_setup -- setup
  exit /b %ERRORLEVEL%
)
echo {"status":"UNAVAILABLE","analysis_mode":"REASONING_ONLY","reason":"CANONICAL_MAX_PYTHON_UNAVAILABLE"}
exit /b 0
