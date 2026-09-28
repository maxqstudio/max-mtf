@echo off
setlocal
cd /d "%~dp0"
title MAX v1.4.0 LangGraph Acceptance
set LANGGRAPH_STRICT_MSGPACK=true
py -3.12 -m acceptance.runners.langgraph_runtime_acceptance --install
if errorlevel 1 goto :fail
echo.
echo LANGGRAPH RUNTIME ACCEPTANCE PASS
echo Evidence: evidence\current\LANGGRAPH_RUNTIME_ACCEPTANCE_v1_3_3.json
pause
exit /b 0
:fail
echo.
echo LANGGRAPH RUNTIME ACCEPTANCE FAIL
echo Evidence: evidence\current\LANGGRAPH_RUNTIME_ACCEPTANCE_v1_3_3.json
pause
exit /b 1
