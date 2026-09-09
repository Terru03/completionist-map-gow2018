param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$BroadWads
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$ExpectedBranch = 'codex/v104-raven-hud-research'
$ExpectedPerm = '7b4ebef237043e97822ffdfc2ba788b0414434514e9ead723622df0fc12a1961'
$ExpectedUiDcb = '40eb9f6fc934b0fb34b568a3fa74bac24b19e6259b2dc5749f26a8cd90865d36'
$ExpectedUiWad = '5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60'
$Tracer = Join-Path $PSScriptRoot 'trace-raven-inworld-resource.py'
$Output = Join-Path $RepoRoot 'build\v0.10.4-raven-inworld-trace\inworld-resource-trace.json'

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return ((Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash).ToLowerInvariant()
}

$branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) {
    throw "Expected Git branch '$ExpectedBranch', found '$branch'."
}

if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before the in-world resource trace so the evidence is from a stable file state.'
}

$Perm = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_perm.dcb'
$UiDcb = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_ui.dcb'
$UiWad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
if ((Get-Sha256 $Perm) -ne $ExpectedPerm) { throw 'wad_r_perm.dcb is not the proven Raven HUD binding state.' }
if ((Get-Sha256 $UiDcb) -ne $ExpectedUiDcb) { throw 'wad_r_ui.dcb is not the proven registered Raven HUD state.' }
if ((Get-Sha256 $UiWad) -ne $ExpectedUiWad) { throw 'r_ui.wad is not the proven Raven HUD WAD.' }

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }
if (-not (Test-Path -LiteralPath $Tracer -PathType Leaf)) { throw "Missing tracer: $Tracer" }

$args = @($Tracer, '--game-root', $GameRoot, '--output', $Output)
if ($BroadWads) { $args += '--broad-wads' }
& $python.Source @args
if ($LASTEXITCODE -ne 0) { throw 'Raven in-world resource trace failed.' }

Write-Host ''
Write-Host 'RAVEN_INWORLD_RESOURCE_TRACE_COMPLETE'
Write-Host "  report: $Output"
Write-Host '  game files written: false'
Write-Host '  next step: inspect DockPoint/SIDE hash topology before creating a Raven in-world resource'
