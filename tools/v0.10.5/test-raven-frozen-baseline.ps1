[CmdletBinding()]
param(
    [string]$BaselineRef = 'origin/release/ravens-v0.10.5-proven'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    throw 'Not inside the Completionist Map repository.'
}

& git -C $RepoRoot fetch origin release/ravens-v0.10.5-proven --quiet
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to fetch frozen Raven baseline.'
}

$Frozen = @(
    'catalogue/odins-ravens.json',
    'catalogue/odins-ravens-save-identities.json',
    'tools/v0.10.5/all-ravens-map-runtime.lua',
    'tools/v0.10.5/all-ravens-gameplay-events.lua'
)

& git -C $RepoRoot diff --quiet $BaselineRef -- $Frozen
if ($LASTEXITCODE -eq 1) {
    & git -C $RepoRoot diff --name-status $BaselineRef -- $Frozen | Out-Host
    throw 'Frozen Raven production files differ from the proven release snapshot.'
}
if ($LASTEXITCODE -ne 0) {
    throw "git diff Raven baseline check failed with exit code $LASTEXITCODE"
}

Write-Host 'RAVEN_FROZEN_BASELINE_PASSED files=4' -ForegroundColor Green
