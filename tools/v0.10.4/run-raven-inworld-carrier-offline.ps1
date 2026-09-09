param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/v104-raven-hud-research'
$ExpectedPerm = '7b4ebef237043e97822ffdfc2ba788b0414434514e9ead723622df0fc12a1961'
$ExpectedUiDcb = '40eb9f6fc934b0fb34b568a3fa74bac24b19e6259b2dc5749f26a8cd90865d36'
$ExpectedUiWad = '5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60'
$ExpectedCoords = '945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb'
$ExpectedGraph = 'd0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Builder = Join-Path $PSScriptRoot 'build-raven-inworld-carrier.py'
$StateDir = Join-Path $RepoRoot 'build\v0.10.4-raven-inworld-carrier'
$Candidate = Join-Path $StateDir 'offline\wad_r_perm.dcb'
$Report = Join-Path $StateDir 'offline\inworld-carrier-offline.json'

$Perm = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_perm.dcb'
$UiDcb = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_ui.dcb'
$UiWad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
$Coords = Join-Path $GameRoot 'exec\dc\pc_le\mapcoords.dcb'
$Graph = Join-Path $GameRoot 'exec\dc\pc_le\compassgraph.dcb'
$SingleActiveManifest = Join-Path $RepoRoot 'build\v0.10.4-raven-single-active-compass-control\active.json'

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return ((Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash).ToLowerInvariant()
}

$branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) {
    throw "Expected Git branch '$ExpectedBranch', found '$branch'."
}

$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -eq 'GoW' -or $_.ProcessName -eq 'GodOfWar'
})
if ($running.Count -gt 0) {
    throw 'God of War is running. Close it so the read-only baseline cannot change during the build.'
}

$checks = @(
    @($Perm, $ExpectedPerm, 'wad_r_perm.dcb'),
    @($UiDcb, $ExpectedUiDcb, 'wad_r_ui.dcb'),
    @($UiWad, $ExpectedUiWad, 'r_ui.wad'),
    @($Coords, $ExpectedCoords, 'mapcoords.dcb'),
    @($Graph, $ExpectedGraph, 'compassgraph.dcb')
)
foreach ($row in $checks) {
    $actual = Get-Sha256 $row[0]
    if ($actual -ne $row[1]) {
        throw "$($row[2]) is not the proven Raven baseline. Expected $($row[1]), got $actual"
    }
}

if (-not (Test-Path -LiteralPath $SingleActiveManifest -PathType Leaf)) {
    throw 'Proven v3 Raven single-active control manifest is not active.'
}
$single = Get-Content -LiteralPath $SingleActiveManifest -Raw | ConvertFrom-Json
if ([string]$single.kind -ne 'completionist-v104-raven-single-active-compass-control' -or $single.schema -ne 3) {
    throw 'Active Raven single-target manifest is not the proven schema-3 control.'
}
$mapTarget = Join-Path $GameRoot 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
if ((Get-Sha256 $mapTarget) -ne ([string]$single.map_after_sha256).ToLowerInvariant()) {
    throw 'Live mapmenu.lua does not match the proven schema-3 single-target control.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }
if (-not (Test-Path -LiteralPath $Builder -PathType Leaf)) { throw "Missing builder: $Builder" }

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Candidate) | Out-Null
& $python.Source $Builder --game-root $GameRoot --output $Candidate --report $Report
if ($LASTEXITCODE -ne 0) { throw 'Offline Raven in-world carrier build failed.' }

$proof = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'OFFLINE_RAVEN_INWORLD_CARRIER_BUILT' -or
    $proof.ready_for_reversible_runtime_install -ne $true -or
    $proof.topology_gates.eight_stock_inworld_exports -ne $true -or
    $proof.topology_gates.stock_inworld_block_contiguous -ne $true -or
    $proof.topology_gates.dock_side_records_differ_only_at_IconName -ne $true -or
    $proof.topology_gates.dock_side_relocation_topology_equal -ne $true -or
    $proof.topology_gates.dock_relocation_self_contained -ne $true -or
    $proof.topology_gates.export_uid_order_strict -ne $true -or
    $proof.topology_gates.existing_relocation_semantics_preserved -ne $true -or
    $proof.topology_gates.normalized_candidate_data_equals_source -ne $true -or
    $proof.game_files_written -ne $false) {
    throw 'Offline Raven in-world carrier contract gate failed.'
}

if ((Get-Sha256 $Perm) -ne $ExpectedPerm) {
    throw 'Live wad_r_perm.dcb changed during offline build.'
}

Write-Host ''
Write-Host 'RAVEN_INWORLD_CARRIER_OFFLINE_GATE_PASSED'
Write-Host "  source:        $($proof.source_sha256)"
Write-Host "  candidate:     $($proof.candidate_sha256)"
Write-Host "  new export:    $($proof.new_export.name)"
Write-Host "  new UID:       $($proof.new_export.uid)"
Write-Host "  root/type:     $($proof.new_export.root) / $($proof.new_export.type_id)"
Write-Host "  Raven InWorld: $($proof.completionist_raven.InWorld_tMPIcon_Name_before) -> $($proof.completionist_raven.InWorld_tMPIcon_Name_after)"
Write-Host '  donor clone differs only at Raven IconName: true'
Write-Host '  stock export/relocation semantics preserved: true'
Write-Host '  game files written: false'
Write-Host '  runtime install performed: false'
Write-Host "  report:        $Report"
Write-Host "  candidate:     $Candidate"
