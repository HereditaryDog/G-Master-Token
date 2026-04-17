param(
    [string]$TargetRef = "",
    [switch]$ForceRedeploy
)

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
$deployMutex = New-Object System.Threading.Mutex($false, "Global\GMasterTokenSyncAndRedeploy")
$mutexAcquired = $false

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logFile -Value "[$timestamp] $Message"
}

function Invoke-Git {
    param([string[]]$Args)
    $output = & $git @Args 2>&1
    if ($LASTEXITCODE -ne 0) {
        $detail = ($output | Out-String).Trim()
        throw "Git command failed: git $($Args -join ' ')`n$detail"
    }
    return ($output | Out-String).Trim()
}

Set-Location $projectRoot

try {
    $mutexAcquired = $deployMutex.WaitOne(0)
    if (-not $mutexAcquired) {
        Write-Log "Another sync or deploy is already running. This run was skipped."
        exit 0
    }

    Write-Log "Starting sync check."

    $status = & $git status --porcelain
    if ($LASTEXITCODE -ne 0) {
        throw "git status failed."
    }
    if ($status) {
        Write-Log "Working tree is dirty. Auto-update skipped."
        exit 0
    }

    Invoke-Git @("fetch", "origin", "--prune", "--tags", "main") | Out-Null

    $currentBranch = Invoke-Git @("branch", "--show-current")
    if (-not $currentBranch) {
        throw "Repository is in detached HEAD state. Please switch back to main before syncing."
    }
    if ($currentBranch -ne "main") {
        Write-Log "Current branch is $currentBranch. Switching to main before deployment."
        Invoke-Git @("switch", "main") | Out-Null
    }

    $local = Invoke-Git @("rev-parse", "HEAD")
    $targetCommit = ""
    $targetLabel = ""

    if ($TargetRef) {
        $targetCommit = Invoke-Git @("rev-parse", "--verify", "$TargetRef^{commit}")
        & $git merge-base --is-ancestor $targetCommit origin/main | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Target ref $TargetRef is not contained in origin/main."
        }

        $targetLabel = $TargetRef
        if ($local -eq $targetCommit) {
            if (-not $ForceRedeploy) {
                Write-Log "Repository already at target ref $TargetRef."
                exit 0
            }
            Write-Log "Force redeploy requested for target ref $TargetRef."
        } else {
            Write-Log "Advancing main to $TargetRef ($targetCommit)."
            Invoke-Git @("merge", "--ff-only", $targetCommit) | Out-Null
        }
    } else {
        $targetCommit = Invoke-Git @("rev-parse", "origin/main")
        $targetLabel = "origin/main"

        if ($local -eq $targetCommit) {
            if (-not $ForceRedeploy) {
                Write-Log "Repository already up to date."
                exit 0
            }
            Write-Log "Force redeploy requested for current origin/main."
        } else {
            Write-Log "New commit detected: $targetCommit"
            Invoke-Git @("pull", "--ff-only", "origin", "main") | Out-Null
        }
    }

    $deployedCommit = Invoke-Git @("rev-parse", "HEAD")

    & $python -m pip install -r requirements.txt | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "pip install failed."
    }

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
        if ($LASTEXITCODE -ne 0) {
            throw "docker compose up failed."
        }
        Write-Log "Docker stack updated to $deployedCommit from $targetLabel."
    } else {
        & $python manage.py migrate --noinput | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "manage.py migrate failed."
        }
        if (Test-Path $nssm) {
            & $nssm restart $serviceName | Out-Null
            if ($LASTEXITCODE -ne 0) {
                throw "Failed to restart Windows service $serviceName."
            }
            Write-Log "Local app service restarted."
        } else {
            Write-Log "NSSM not installed; code updated but local service not restarted automatically."
        }
    }

    Write-Log "Deployment updated to $deployedCommit from $targetLabel."
} finally {
    if ($mutexAcquired) {
        $deployMutex.ReleaseMutex() | Out-Null
    }
    $deployMutex.Dispose()
}
