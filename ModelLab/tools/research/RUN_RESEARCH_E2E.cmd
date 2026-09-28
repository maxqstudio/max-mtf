@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."
set "POWERSHELL=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%POWERSHELL%" set "POWERSHELL=powershell.exe"
echo ============================================================
echo MAX Research E2E - E2E_WORKFLOW_TEST_V1
echo Synthetic sandbox only - NOT production scientific evidence
echo ============================================================
"%POWERSHELL%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0RUN_RESEARCH_E2E.ps1"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo E2E RESULT: PASS
) else (
  echo E2E RESULT: FAIL ^(exit code %RC%^)
)
echo Diagnostic evidence is under:
echo   %~dp0..\..\runtime\research_e2e\diagnostic_evidence\
echo.
pause
exit /b %RC%
