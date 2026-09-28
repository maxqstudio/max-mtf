@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo MAX MTF v2.0.1 - MTF-1 OWNER MT5 EXECUTION ACCEPTANCE
echo Starts one closure run and requires fresh local acceptance.
echo ============================================================
python -m mtf.mtf1_closure_run --start
set RC=%ERRORLEVEL%
if NOT %RC% EQU 0 goto :done
python -m acceptance.runners.run_acceptance
set RC=%ERRORLEVEL%
if NOT %RC% EQU 0 goto :done
python -m acceptance.runners.owner_mtf1_runtime_acceptance
set RC=%ERRORLEVEL%
if NOT %RC% EQU 0 goto :done
python -m acceptance.runners.owner_mtf1_runtime_acceptance --verify-existing
set RC=%ERRORLEVEL%
:done
pause
exit /b %RC%
