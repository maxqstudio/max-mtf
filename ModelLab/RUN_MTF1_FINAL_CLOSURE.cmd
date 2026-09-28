@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHONPATH=%~dp0;%PYTHONPATH%"
title Max MTF v2.0.1 - MTF-1 Final Closure

echo ============================================================
echo MAX MTF v2.0.1 - MTF-1 ONE-CLICK FINAL CLOSURE
echo Canonical Python 3.12 + MAX venv bootstrap is mandatory.
echo Every closure stage uses one canonical venv interpreter.
echo ============================================================

where python >nul 2>&1
if errorlevel 1 goto :try_py_launcher
python -c "import sys" >nul 2>&1
if errorlevel 1 goto :try_py_launcher
python -m mtf.mtf1_closure_bootstrap
set "RC=%errorlevel%"
goto :done

:try_py_launcher
where py >nul 2>&1
if errorlevel 1 goto :no_bootstrap
py -c "import sys" >nul 2>&1
if errorlevel 1 goto :no_bootstrap
py -m mtf.mtf1_closure_bootstrap
set "RC=%errorlevel%"
goto :done

:no_bootstrap
echo.
echo Tidak ada Python bootstrap yang dapat dijalankan.
echo Install Python/Python Launcher agar bootstrap dapat resolve Python 3.12 canonical MAX venv.
set "RC=103"

:done
echo.
if "%RC%"=="0" (
  echo MTF-1 FINAL CLOSURE PASS - MTF_1_CLOSED
) else (
  echo MTF-1 FINAL CLOSURE FAIL - MTF-2 REMAINS BLOCKED
)
pause
endlocal & exit /b %RC%
