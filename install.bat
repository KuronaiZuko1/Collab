@echo off
title BANDI Installation
echo =====================================================================
echo    BANDI - Local-First Trading Intelligence Installation
echo =====================================================================
echo.

:: Check Python installation
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in system PATH.
    echo Please install Python 3.10+ from python.org and check "Add Python to PATH".
    pause
    exit /b 1
)

echo [1/4] Installing required Python packages from requirements.txt...
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

echo [2/4] Initializing SQLite database schema...
python -c "from bandi.database import db; db.init_db(); print('Database schema ready.')"

echo [3/4] Compiling Bandi.mq5 for MetaTrader 5...
python -c "from bandi.mt5.compiler import mql5_compiler; res = mql5_compiler.compile_ea(); print('MT5 EA Compilation status:', res.get('ok'))"

echo [4/4] Syncing economic calendar releases...
python -c "from bandi.calendar import calendar_client; res = calendar_client.fetch_and_sync(force=True); print('Calendar synced:', res.get('count'), 'events')"

echo.
echo =====================================================================
echo    INSTALLATION COMPLETE!
echo    You can now run "start.bat" to launch BANDI.
echo =====================================================================
pause
