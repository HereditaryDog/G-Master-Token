$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $projectRoot "scripts\sync-and-redeploy.ps1"
$taskName = "web001-auto-sync"
$taskCommand = "powershell.exe -ExecutionPolicy Bypass -File `"$scriptPath`""

schtasks.exe /Delete /TN $taskName /F *> $null
schtasks.exe /Create /SC MINUTE /MO 30 /TN $taskName /TR $taskCommand /F | Out-Null

Write-Output "Registered scheduled task: $taskName"
