# TN Bridge Watchdog — runs forever, restarts tn2.py immediately on any exit
# Registered in Task Scheduler as TN_Bridge_Watchdog
# This script itself is what Task Scheduler runs — tn2.py never needs to be in Task Scheduler directly

$script = "C:\Users\TNap7\tn2.py"
$python = "python"

Write-Host "$(Get-Date) Watchdog started" -ForegroundColor Green

while ($true) {
    Write-Host "$(Get-Date) Starting tn2.py..." -ForegroundColor Cyan
    try {
        & $python $script
        $exit = $LASTEXITCODE
        Write-Host "$(Get-Date) tn2.py exited with code $exit — restarting in 3 seconds..." -ForegroundColor Yellow
    } catch {
        Write-Host "$(Get-Date) tn2.py threw exception: $_ — restarting in 3 seconds..." -ForegroundColor Red
    }
    Start-Sleep -Seconds 3
}
