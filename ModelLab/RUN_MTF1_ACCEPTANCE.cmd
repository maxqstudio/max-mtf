@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo Max MTF v2.0.1 - MTF-1 Data Foundation Acceptance
echo ============================================================
python -m acceptance.runners.run_acceptance
set RC=%ERRORLEVEL%
echo.
if %RC%==0 (echo MTF-1 SOURCE/CONTRACT ACCEPTANCE PASS) else (echo MTF-1 ACCEPTANCE FAIL)
pause
exit /b %RC%
