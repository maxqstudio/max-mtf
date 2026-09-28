@echo off
setlocal
cd /d "%~dp0"
title MAX v1.4.0 CUDA Runtime Acceptance
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher not found. Run START_UI.cmd first.
  pause
  exit /b 1
)
py -3.12 -m acceptance.runners.cuda_runtime_acceptance
set RC=%ERRORLEVEL%
echo.
echo Evidence: evidence\current\CUDA_RUNTIME_ACCEPTANCE_v1_3_3.json
if not "%RC%"=="0" echo CUDA acceptance FAILED. Upload the JSON evidence for audit.
if "%RC%"=="0" echo CUDA acceptance PASS. Upload the JSON evidence for audit.
pause
exit /b %RC%
