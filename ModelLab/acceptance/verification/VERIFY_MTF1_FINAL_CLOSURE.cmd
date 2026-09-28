@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================
echo MAX MTF v2.0.1 - READ-ONLY VERIFY EXISTING MTF-1 CLOSURE
echo This command NEVER creates, repairs, regenerates, or overwrites evidence.
echo ============================================================
python -m mtf.mtf1_final_closure --verify-existing
set RC=%ERRORLEVEL%
pause
exit /b %RC%
