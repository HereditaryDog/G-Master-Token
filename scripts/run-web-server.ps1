$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$venvPath = if (Test-Path (Join-Path $projectRoot ".venv-service\Scripts\python.exe")) {
    Join-Path $projectRoot ".venv-service\Scripts"
} else {
    Join-Path $projectRoot ".venv\Scripts"
}
$python = Join-Path $venvPath "python.exe"

Set-Location $projectRoot

& $python manage.py migrate --noinput
& $python manage.py collectstatic --noinput
& $python -c "from waitress import serve; from config.wsgi import application; serve(application, listen='127.0.0.1:8000')"
