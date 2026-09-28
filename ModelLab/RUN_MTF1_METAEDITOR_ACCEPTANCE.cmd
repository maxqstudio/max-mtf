@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo MAX MTF v2.0.1 - MTF-1 METAEDITOR EXECUTION ACCEPTANCE
echo Reuses active closure run or creates one when none exists.
echo ============================================================
python -m mtf.mtf1_closure_run --ensure
set RC=%ERRORLEVEL%
if NOT %RC% EQU 0 goto :done
python -m acceptance.runners.run_acceptance
set RC=%ERRORLEVEL%
if NOT %RC% EQU 0 goto :done
python -m acceptance.runners.owner_mtf1_metaeditor_acceptance
set RC=%ERRORLEVEL%
if NOT %RC% EQU 0 goto :done
python -m acceptance.runners.owner_mtf1_metaeditor_acceptance --verify-existing
set RC=%ERRORLEVEL%
:done
pause
exit /b %RC%
