param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/v104-raven-production'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Verifier = Join-Path $PSScriptRoot 'verify-raven-production-state.py'
$StateDir = Join-Path $RepoRoot 'build\v0.10.4-raven-production'
$Report = Join-Path $StateDir 'production-state.json'

$branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) {
    throw "Expected Git branch '$ExpectedBranch', found '$branch'."
}

$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -eq 'GoW' -or $_.ProcessName -eq 'GodOfWar'
})
if ($running.Count -gt 0) {
    throw 'God of War is running. Close it before freezing the production baseline.'
}

if (-not (Test-Path -LiteralPath $Verifier -PathType Leaf)) {
    throw "Missing verifier: $Verifier"
}
$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) { throw 'Python 3 is required.' }

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

& $python.Source $Verifier --game-root $GameRoot --repo-root $RepoRoot --output $Report
if ($LASTEXITCODE -ne 0) { throw 'Raven production-state verification failed.' }
if (-not (Test-Path -LiteralPath $Report -PathType Leaf)) { throw 'Verifier did not create its report.' }

$proof = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'RAVEN_PRODUCTION_STATE_VERIFIED' -or
    $proof.ready_to_adopt_as_production_baseline -ne $true -or
    $proof.wad_r_ui_contract.raven_hud.capacity -ne 2 -or
    $proof.proven_invariants.single_active_target -ne $true -or
    $proof.proven_invariants.native_pathfinding -ne $true -or
    $proof.game_files_written -ne $false) {
    throw 'Production-state report did not satisfy the final Raven contract.'
}

Write-Host ''
Write-Host 'RAVEN_PRODUCTION_GATE_PASSED'
Write-Host "  wad_r_perm.dcb: $($proof.live_hashes.'wad_r_perm.dcb')"
Write-Host "  wad_r_ui.dcb:   $($proof.live_hashes.'wad_r_ui.dcb')"
Write-Host "  r_ui.wad:       $($proof.live_hashes.'r_ui.wad')"
Write-Host "  mapmenu.lua:    $($proof.live_hashes.'mapmenu.lua')"
Write-Host '  custom map/HUD/in-world Raven: verified'
Write-Host '  native distance/pathfinding: runtime-proven'
Write-Host '  single-target Add/Replace/Remove: runtime-proven'
Write-Host '  game files written: false'
Write-Host "  report: $Report"
