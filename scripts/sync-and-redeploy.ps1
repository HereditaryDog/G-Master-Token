$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $projectRoot "logs"
$logFile = Join-Path $logDir "sync-and-redeploy.log"
$serviceName = "web001-app"
$git = "C:\Program Files\Git\cmd\git.exe"
$venvPath = if (Test-Path (Join-Path $projectRoot ".venv-service\Scripts\python.exe")) {
    Join-Path $projectRoot ".venv-service\Scripts"
} else {
    Join-Path $projectRoot ".venv\Scripts"
}
$python = Join-Path $venvPath "python.exe"
$docker = "docker"
$nssm = "$env:LOCALAPPDATA\Microsoft\WinGet\Links\nssm.exe"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logFile -Value "[$timestamp] $Message"
}

Set-Location $projectRoot

Write-Log "Starting sync check."

$status = & $git status --porcelain
if ($status) {
    Write-Log "Working tree is dirty. Auto-update skipped."
    exit 0
}

& $git fetch origin main | Out-Null
$local = (& $git rev-parse HEAD).Trim()
$remote = (& $git rev-parse origin/main).Trim()

if ($local -eq $remote) {
    Write-Log "Repository already up to date."
    exit 0
}

Write-Log "New commit detected: $remote"
& $git pull --ff-only origin main | Out-Null

& $python -m pip install -r requirements.txt | Out-Null

$dockerAvailable = $false
try {
    & $docker --version | Out-Null
    $dockerAvailable = $true
} catch {
    $dockerAvailable = $false
}

if ($dockerAvailable -and (Test-Path ".env.server")) {
    $composeArgs = @("compose", "--env-file", ".env.server", "up", "-d", "--build")
    if ((Get-Content ".env.server") -match "^CLOUDFLARE_TUNNEL_TOKEN=.+") {
        $composeArgs = @("compose", "--env-file", ".env.server", "--profile", "public", "up", "-d", "--build")
    }
    & $docker @composeArgs | Out-Null
    Write-Log "Docker stack updated to $remote"
} else {
    & $python manage.py migrate --noinput | Out-Null
    if (Test-Path $nssm) {
        & $nssm restart $serviceName | Out-Null
        Write-Log "Local app service restarted."
    } else {
        Write-Log "NSSM not installed; code updated but local service not restarted automatically."
    }
}

Write-Log "Deployment updated to $remote"
