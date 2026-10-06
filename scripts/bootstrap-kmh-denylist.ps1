# Erzeugt/aktualisiert ~/.config/kmh-denylist.txt aus Safe-CLI denylist.txt (lokal, gitignored).
# Standard: Teilstring unveraendert. Nur Zeilen mit fuehrendem = in der Quelle bleiben =Wort.
param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$SafeDeny = Join-Path (Split-Path -Parent $RepoRoot) "Safe-CLI-Helpers\git-hooks\denylist.txt"
$ConfigDir = Join-Path $env:USERPROFILE ".config"
$KmhDeny = Join-Path $ConfigDir "kmh-denylist.txt"

. (Join-Path $PSScriptRoot "bootstrap-kmh-denylist-lib.ps1")

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
    '# kmh-denylist - local only, never commit'
    '# From Safe-CLI denylist.txt - default substr; = only if source line starts with ='
    '# Domains: leading @ stripped. UTF-8 no BOM. Broad words: add = manually in this file.'
    ''
)

$entries = New-Object System.Collections.Generic.List[string]
foreach ($line in Get-Content -LiteralPath $SafeDeny -Encoding UTF8) {
    $converted = Convert-SafeCliDenyLineToKmh -Line $line
    if ($null -ne $converted) {
        $entries.Add($converted) | Out-Null
    }
}

$BroadFile = Join-Path $ConfigDir "kmh-denylist-broad-words.txt"
$broad = Read-KmhBroadWordTokens -BroadWordsFile $BroadFile
Apply-KmhBroadWordPrefixes -Entries $entries -BroadTokens $broad
if ($broad.Count -gt 0) {
    Write-Host "Broad-word overlay: $($broad.Count) tokens from $BroadFile"
} elseif (-not (Test-Path $BroadFile)) {
    Write-Host "Hinweis: $BroadFile fehlt - breite Begriffe bleiben Teilstring (Vorlage scripts/kmh-denylist-broad-words.example.txt)"
}

$utf8NoBom = New-Object System.Text.UTF8Encoding $false
$body = ($header + $entries) -join [Environment]::NewLine
[System.IO.File]::WriteAllText($KmhDeny, $body + [Environment]::NewLine, $utf8NoBom)

Write-Host "kmh-denylist: $($entries.Count) entries -> $KmhDeny"
Write-Host 'Test: "C:\Program Files\Git\bin\bash.exe" scripts/test-kmh-denylist-hook-live.sh'
