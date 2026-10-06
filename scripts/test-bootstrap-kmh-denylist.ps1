# Self-test: Bootstrap uebernimmt Zeilen als Teilstring; = nur aus Quelle.
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "bootstrap-kmh-denylist-lib.ps1")

function Assert-Eq {
    param($Name, $Expected, $Actual)
    if ($Expected -ne $Actual) {
        Write-Error "FAIL $Name : expected '$Expected' got '$Actual'"
    }
    Write-Host "ok: $Name"
}

Assert-Eq "comment skipped" $null (Convert-SafeCliDenyLineToKmh -Line "# foo")
Assert-Eq "domain strip @" "beispiel-uni.example" (Convert-SafeCliDenyLineToKmh -Line "@beispiel-uni.example")
Assert-Eq "alpha unchanged" "tokenalpha" (Convert-SafeCliDenyLineToKmh -Line "tokenalpha")
Assert-Eq "equals preserved" "=ExampleTown" (Convert-SafeCliDenyLineToKmh -Line "=ExampleTown")
Assert-Eq "underscore token" "needle_sub" (Convert-SafeCliDenyLineToKmh -Line "needle_sub")

Write-Host "bootstrap-kmh-denylist transform: PASS"
