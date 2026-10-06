# Repo-lokale Hooks: kmh-denylist (~/.config/kmh-denylist.txt) + Safe-CLI-Helpers pre-commit
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$HooksDir = Join-Path $RepoRoot ".githooks"

if (-not (Test-Path $HooksDir)) {
    Write-Error ".githooks fehlt in $RepoRoot"
}

Push-Location $RepoRoot
try {
    git config core.hooksPath .githooks
    Write-Host "core.hooksPath -> .githooks (dieses Repo)"
    Write-Host "Sperrliste: `$env:USERPROFILE\.config\kmh-denylist.txt (oder KMH_DENYLIST_FILE)"
    Write-Host "Test: bash scripts/test-kmh-denylist-hook.sh && bash scripts/test-kmh-denylist-hook-cases.sh"
} finally {
    Pop-Location
}
