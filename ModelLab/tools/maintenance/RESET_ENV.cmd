@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."
title ComplexPolicy Reset Environment v0.6.6

echo Menghapus environment ComplexPolicy. Python sistem TIDAK disentuh.

if defined CPML_VENV (
  if exist "%CPML_VENV%" rmdir /s /q "%CPML_VENV%"
)

for %%D in (C D E F G H I J K L M N O P Q R S T U V W X Y Z) do (
  if exist "%%D:\.cpml\venv312" rmdir /s /q "%%D:\.cpml\venv312"
)

if defined LOCALAPPDATA (
  if exist "%LOCALAPPDATA%\CPML\venv312" rmdir /s /q "%LOCALAPPDATA%\CPML\venv312"
)

if exist ".venv" rmdir /s /q ".venv"
if exist "bootstrap.log" del /q "bootstrap.log" >nul 2>&1

echo Environment research sudah dibersihkan.
call "%CD%\START_UI.cmd"
set "RC=%errorlevel%"
endlocal & exit /b %RC%
