# Einmaliger Neustart: ein Commit, keine alte History — nur ausführen, wenn das
# NEUE leere GitHub-Repo existiert und origin darauf zeigt (altes Repo vorher löschen/archivieren).
#
#   git remote set-url origin https://github.com/<user>/<neues-repo>.git
#   pwsh -File scripts/git-single-commit-push.ps1
#
# Danach lokal alte Objekte entfernen (optional):
#   git reflog expire --expire=now --all
#   git gc --prune=now --aggressive

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .git)) { throw "Kein Git-Repo in $(Get-Location)" }

$remote = (git remote get-url origin 2>$null)
if (-not $remote) { throw "origin fehlt — zuerst git remote add origin <URL>" }

Write-Host "Remote: $remote"
Write-Host "Orphan-Branch main (ein Commit, kein History-Import)..."

git checkout --orphan main-fresh
git add -A
git status --short
git commit -m "Initial commit: KI-Mail-Helper (Ordner-Audit)"

git branch -D main 2>$null
git branch -m main

Write-Host "Push (force) — nur wenn origin das NEUE leere Repo ist:"
Write-Host "  git push -u origin main --force"
Write-Host "Nicht ausführen, wenn origin noch das alte Repo ist."
