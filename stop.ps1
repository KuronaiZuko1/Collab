# BANDI Stop Script for PowerShell
Write-Host "Stopping BANDI processes on port 8000..." -ForegroundColor Yellow

$connections = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($connections) {
    foreach ($conn in $connections) {
        Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped process ID $($conn.OwningProcess)" -ForegroundColor Green
    }
} else {
    Write-Host "No active BANDI server found running on port 8000." -ForegroundColor Cyan
}
