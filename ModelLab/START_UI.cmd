@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Max MTF · v2.0.1

echo [BOOT] Menjalankan bootstrap runtime...

where python >nul 2>&1
if errorlevel 1 goto :try_py_launcher
python -c "import sys" >nul 2>&1
if errorlevel 1 goto :try_py_launcher
python -m ui.ui_bootstrap
set "RC=%errorlevel%"
goto :done

:try_py_launcher
where py >nul 2>&1
if errorlevel 1 goto :no_bootstrap
py -c "import sys" >nul 2>&1
if errorlevel 1 goto :no_bootstrap
py -m ui.ui_bootstrap
set "RC=%errorlevel%"
goto :done

:no_bootstrap
echo.
echo Tidak ada Python bootstrap yang dapat dijalankan.
echo Install Python 3.12 atau Python launcher, lalu jalankan file ini lagi.
set "RC=103"

:done
if "%RC%"=="0" goto :exit_ok
echo.
echo Model Lab berhenti dengan error code %RC%.
if exist "bootstrap.log" echo Detail: %CD%\bootstrap.log
pausE

:exit_ok
endlocal & exit /b %RC%
