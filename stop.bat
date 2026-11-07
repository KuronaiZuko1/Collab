@echo off
title Stop BANDI
echo Stopping any running BANDI / Uvicorn server processes on Windows...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo BANDI services stopped.
pause
