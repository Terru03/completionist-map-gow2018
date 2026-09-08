param([ValidateNotNullOrEmpty()][string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar')

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
$python = Get-Command python -ErrorAction Stop
$builder = Join-Path $PSScriptRoot 'build-raven-compass-hud-three-payload-v3.py'
$candidate = Join-Path $repo 'build\v0.10.4\raven-compass-hud-three-payload-v3\r_ui.wad'
$report = Join-Path $repo 'archive\field-logs\completionist-v104-raven-compass-hud-three-payload-v3.json'

Write-Host 'Read-only v3 gate: inspect full groups, test clone edits in memory.'
& $python.Source $builder --game-root $GameRoot --output-wad $candidate --report $report
$gateExit = $LASTEXITCODE
if ($gateExit -eq 3) {
    Write-Host 'Gate BLOCKED by source topology. No candidate built. Do not install or launch for this test.'
    exit 3
}
if ($gateExit -ne 0) { throw 'Offline Raven HUD preflight failed.' }
throw 'Unexpected success from blocked v3 preflight; inspect source and report.'
