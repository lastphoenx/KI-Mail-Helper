function Convert-SafeCliDenyLineToKmh {
    param([string]$Line)
    $t = $Line -replace '^\uFEFF', ''
    $t = $t.Trim()
    if ($t -eq '' -or $t.StartsWith('#')) { return $null }
    if ($t.StartsWith('@')) { $t = $t.Substring(1).Trim() }
    if ($t -eq '') { return $null }
    return $t
}
