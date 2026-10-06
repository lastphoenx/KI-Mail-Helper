# Erzeugt/aktualisiert ~/.config/kmh-denylist.txt aus Safe-CLI denylist.txt (lokal, gitignored).
# Gibt Sperrmuster nicht aus. Kurze Begriffe ggf. manuell mit = prefix versehen.
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$SafeDeny = Join-Path (Split-Path -Parent $RepoRoot) "Safe-CLI-Helpers\git-hooks\denylist.txt"
$ConfigDir = Join-Path $env:USERPROFILE ".config"
$KmhDeny = Join-Path $ConfigDir "kmh-denylist.txt"

if (-not (Test-Path $SafeDeny)) {
    Write-Error "Safe-CLI denylist fehlt: $SafeDeny"
}

New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null

if ((Test-Path $KmhDeny) -and -not $Force) {
    $existing = Get-Content -LiteralPath $KmhDeny -ErrorAction SilentlyContinue |
        Where-Object { $_ -match '\S' -and $_ -notmatch '^\s*#' }
    if ($existing.Count -gt 0) {
        Write-Host "Behalte $KmhDeny ($($existing.Count) active lines). Neu: -Force"
        exit 0
    }
}

$header = @(
    '# kmh-denylist — local only, never commit'
    '# From Safe-CLI denylist.txt — substr; =word; domains without leading @'
    '# UTF-8 no BOM'
    ''
)

$entries = New-Object System.Collections.Generic.List[string]
foreach ($line in Get-Content -LiteralPath $SafeDeny -Encoding UTF8) {
    $t = $line -replace '^\uFEFF', ''
    $t = $t.Trim()
    if ($t -eq '' -or $t.StartsWith('#')) { continue }
    if ($t.StartsWith('@')) { $t = $t.Substring(1).Trim() }
    if ($t -eq '') { continue }
    if ($t -notmatch '^=' -and $t -match '^[A-Za-z]{2,20}$') {
        $t = "=$t"
    }
    $entries.Add($t) | Out-Null
}

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$body = ($header + $entries) -join [Environment]::NewLine
[System.IO.File]::WriteAllText($KmhDeny, $body + [Environment]::NewLine, $utf8NoBom)

Write-Host "kmh-denylist: $($entries.Count) entries -> $KmhDeny"
Write-Host 'Test: "C:\Program Files\Git\bin\bash.exe" scripts/test-kmh-denylist-hook-live.sh'
