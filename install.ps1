# BANDI Installation Script for PowerShell
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "   BANDI - Local-First Trading Intelligence Installation" -ForegroundColor Cyan
Write-Host "=====================================================================" -ForegroundColor Cyan

python --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Python is not installed or not in system PATH." -ForegroundColor Red
    exit 1
}

Write-Host "`n[1/4] Installing Python dependencies..." -ForegroundColor Yellow
python -m pip install -r requirements.txt

Write-Host "`n[2/4] Initializing SQLite database schema..." -ForegroundColor Yellow
python -c "from bandi.database import db; db.init_db(); print('Database schema ready.')"

Write-Host "`n[3/4] Compiling Bandi.mq5 for MetaTrader 5..." -ForegroundColor Yellow
python -c "from bandi.mt5.compiler import mql5_compiler; res = mql5_compiler.compile_ea(); print('MT5 EA Compilation status:', res.get('ok'))"

Write-Host "`n[4/4] Syncing economic calendar releases..." -ForegroundColor Yellow
python -c "from bandi.calendar import calendar_client; res = calendar_client.fetch_and_sync(force=True); print('Calendar synced:', res.get('count'), 'events')"

Write-Host "`n=====================================================================" -ForegroundColor Green
Write-Host "   INSTALLATION COMPLETE! Run .\start.ps1 to launch BANDI." -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Green
