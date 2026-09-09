param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ExpectedBranch = 'codex/v104-raven-hud-research'
$Inspector = Join-Path $PSScriptRoot 'inspect-raven-inworld-export-topology.py'
$OutDir = Join-Path $RepoRoot 'build\v0.10.4-raven-inworld-export-topology'
$Report = Join-Path $OutDir 'inworld-export-topology.json'

$branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) {
    throw "Expected branch '$ExpectedBranch', found '$branch'."
}

$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -eq 'GoW' -or $_.ProcessName -eq 'GodOfWar'
})
if ($running.Count -gt 0) {
    throw 'Close God of War before running the in-world export topology inspector.'
}

if (-not (Test-Path -LiteralPath $Inspector -PathType Leaf)) {
    throw "Missing inspector: $Inspector"
}
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
& $python.Source $Inspector --game-root $GameRoot --output $Report
if ($LASTEXITCODE -ne 0) { throw 'Raven in-world export topology inspection failed.' }

$proof = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'READ_ONLY_RAVEN_INWORLD_EXPORT_TOPOLOGY' -or
    $proof.game_files_written -ne $false -or
    $proof.saves_progression_marker_state_written -ne $false) {
    throw 'Read-only in-world topology report failed its contract.'
}

Write-Host ''
Write-Host 'RAVEN_INWORLD_EXPORT_TOPOLOGY_COMPLETE'
Write-Host ("  clone design gate: {0}" -f $(if ($proof.clone_gate.ready_to_design_offline_raven_inworld_clone) { 'READY' } else { 'NOT_READY' }))
Write-Host "  report: $Report"
Write-Host '  game files written: false'
