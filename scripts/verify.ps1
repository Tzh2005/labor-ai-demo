[CmdletBinding()]
param(
    [switch]$SkipPipCheck
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    Write-Host "[1/3] Python syntax"
    python -m py_compile app.py ai_service.py conversation_store.py knowledge_base.py check_environment.py

    Write-Host "[2/3] Unit and security tests"
    python -m unittest discover -s tests -v

    if (-not $SkipPipCheck) {
        Write-Host "[3/3] Dependency consistency"
        python -m pip check
    }

    Write-Host "Verification passed." -ForegroundColor Green
}
finally {
    Pop-Location
}
