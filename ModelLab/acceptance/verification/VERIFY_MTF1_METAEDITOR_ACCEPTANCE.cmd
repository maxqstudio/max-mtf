@echo off
setlocal
cd /d "%~dp0..\.."
echo ============================================================
echo MAX MTF v2.0.1 - VERIFY EXISTING MTF-1 METAEDITOR EVIDENCE
echo ============================================================
python -m acceptance.runners.owner_mtf1_metaeditor_acceptance --verify-existing
set RC=%ERRORLEVEL%
pause
exit /b %RC%
