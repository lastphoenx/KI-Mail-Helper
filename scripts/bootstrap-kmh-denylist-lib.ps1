function Convert-SafeCliDenyLineToKmh {
    param([string]$Line)
    $t = $Line -replace '^\uFEFF', ''
    $t = $t.Trim()
    if ($t -eq '' -or $t.StartsWith('#')) { return $null }
    if ($t.StartsWith('@')) { $t = $t.Substring(1).Trim() }
    if ($t -eq '') { return $null }
    return $t
}

function Read-KmhBroadWordTokens {
    param([string]$BroadWordsFile)
    $tokens = New-Object System.Collections.Generic.List[string]
    if (-not (Test-Path $BroadWordsFile)) {
        return $tokens
    }
    foreach ($line in Get-Content -LiteralPath $BroadWordsFile -Encoding UTF8) {
        $t = ($line -replace '^\uFEFF', '').Trim()
        if ($t -eq '' -or $t.StartsWith('#')) { continue }
        if ($t.StartsWith('=')) { $t = $t.Substring(1).Trim() }
        if ($t -ne '') { $tokens.Add($t) | Out-Null }
    }
    return $tokens
}

function Apply-KmhBroadWordPrefixes {
    param(
        [System.Collections.Generic.List[string]]$Entries,
        [System.Collections.Generic.List[string]]$BroadTokens
    )
    if ($BroadTokens.Count -eq 0) { return }
    $want = @{}
    foreach ($b in $BroadTokens) {
        $want[$b.ToLowerInvariant()] = $true
    }
    for ($i = 0; $i -lt $Entries.Count; $i++) {
        $e = $Entries[$i]
        if ($e.StartsWith('=')) { continue }
        if ($want.ContainsKey($e.ToLowerInvariant())) {
            $Entries[$i] = "=$e"
        }
    }
}
