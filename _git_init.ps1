$ErrorActionPreference = "Stop"
$git = "C:\Program Files\Git\cmd\git.exe"
Set-Location "C:\Monitoring Software"

& $git init 2>&1 | Out-Host
& $git symbolic-ref HEAD refs/heads/main 2>&1 | Out-Host

# Repo-local identity only (does not modify global git config).
& $git config user.email "dev@monitoringsoftware.local" 2>&1 | Out-Host
& $git config user.name "MonitoringSoftware Dev" 2>&1 | Out-Host

& $git add -A 2>&1 | Out-Host
& $git commit -m "Initial commit: Remote Workforce Monitoring platform (phases 0-9)" 2>&1 | Out-Host

Write-Host "=== STATUS ==="
& $git status --short --branch 2>&1 | Out-Host
Write-Host "=== FILE COUNT ==="
(& $git ls-files).Count
