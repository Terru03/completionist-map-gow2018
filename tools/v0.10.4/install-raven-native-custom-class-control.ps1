param(
    [ValidateSet('Install','Remove')][string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before installing or removing the Raven native custom-class control.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$mapTarget = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$coordsTarget = Join-Path $game 'exec\dc\pc_le\mapcoords.dcb'
$graphTarget = Join-Path $game 'exec\dc\pc_le\compassgraph.dcb'
$permTarget = Join-Path $game 'exec\dc\pc_le\wad_r_perm.dcb'
$wadTarget = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$patcher = Join-Path $PSScriptRoot 'patch-raven-native-custom-class-control.py'
$stateDir = Join-Path $repo 'build\v0.10.4-raven-native-custom-class-control'
$backup = Join-Path $stateDir 'mapmenu-before.lua'
$candidate = Join-Path $stateDir 'mapmenu-custom-class.lua'
$report = Join-Path $stateDir 'custom-class-control.json'
$manifestPath = Join-Path $stateDir 'active.json'
$routeManifestPath = Join-Path $repo 'build\v0.10.4-raven-native-route-reproof\active.json'
$abStateRoot = Join-Path $repo 'build\v0.10.4\native-raven-no-render\ab-transactions'

$expectedMap = 'd101bb60807ad95919e42d92e3155ea9e7bda9c713bc1cad646b932d6f7c928d'
$expectedCoords = '945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb'
$expectedGraph = 'd0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68'
$expectedPerm = '7b4ebef237043e97822ffdfc2ba788b0414434514e9ead723622df0fc12a1961'
$expectedWad = '5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60'

function Hash-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

if (-not (Test-Path -LiteralPath $mapTarget -PathType Leaf)) { throw "Missing installed mapmenu.lua: $mapTarget" }

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Raven native custom-class control is already removed.'
        return
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $before = ([string]$manifest.map_before_sha256).ToLowerInvariant()
    $after = ([string]$manifest.map_after_sha256).ToLowerInvariant()
    $current = Hash-File $mapTarget
    if ($current -ne $after -and $current -ne $before) {
        throw 'mapmenu.lua changed after custom-class control install. Refusing automatic overwrite.'
    }
    if ((Hash-File $backup) -ne $before) { throw 'Custom-class control backup hash mismatch.' }
    if ($current -eq $after) {
        Copy-Item -LiteralPath $backup -Destination $mapTarget -Force
    }
    if ((Hash-File $mapTarget) -ne $before) { throw 'Custom-class control rollback hash mismatch.' }
    $removed = Join-Path $stateDir ('removed-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Raven native custom-class control removed. mapmenu.lua restored byte-for-byte.'
    Write-Host '- native mapcoords/compassgraph A/B left installed: true'
    Write-Host '- WAD/DCB artwork files touched: false'
    Write-Host '- saves/progression/marker state touched: false'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Raven native custom-class control is already installed.'
}
if (-not (Test-Path -LiteralPath $patcher -PathType Leaf)) { throw "Missing patcher: $patcher" }
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }
if (-not (Test-Path -LiteralPath $routeManifestPath -PathType Leaf)) {
    throw 'Native Raven route re-proof manifest is missing; refusing class-only stacking.'
}
$routeManifest = Get-Content -LiteralPath $routeManifestPath -Raw | ConvertFrom-Json
if ([string]$routeManifest.kind -ne 'completionist-v104-raven-native-route-reproof') {
    throw 'Unexpected native route re-proof manifest kind.'
}
if (([string]$routeManifest.map_after_sha256).ToLowerInvariant() -ne $expectedMap) {
    throw 'Native route re-proof manifest does not match the pinned working mapmenu baseline.'
}

$installedAB = @()
if (Test-Path -LiteralPath $abStateRoot -PathType Container) {
    Get-ChildItem -LiteralPath $abStateRoot -Recurse -Filter manifest.json -File | ForEach-Object {
        try {
            $v = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
            if ([string]$v.kind -eq 'v104-native-raven-coordinate-graph-ab-v1' -and [string]$v.state -eq 'installed') {
                $installedAB += $_.FullName
            }
        } catch {}
    }
}
if ($installedAB.Count -ne 1) {
    throw "Expected exactly one installed native Raven coordinate/graph A/B transaction, found $($installedAB.Count)."
}

$checks = @(
    @($mapTarget, $expectedMap, 'mapmenu.lua'),
    @($coordsTarget, $expectedCoords, 'mapcoords.dcb'),
    @($graphTarget, $expectedGraph, 'compassgraph.dcb'),
    @($permTarget, $expectedPerm, 'wad_r_perm.dcb'),
    @($wadTarget, $expectedWad, 'r_ui.wad')
)
foreach ($row in $checks) {
    $actual = Hash-File $row[0]
    if ($actual -ne $row[1]) {
        throw "$($row[2]) hash differs from the proven custom-class test baseline. Expected $($row[1]), got $actual"
    }
}

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
Copy-Item -LiteralPath $mapTarget -Destination $backup -Force
if ((Hash-File $backup) -ne $expectedMap) { throw 'Custom-class control backup verification failed.' }

Write-Host 'Building class-only native Raven control offline...'
& $python.Source $patcher --input $mapTarget --output $candidate --report $report
if ($LASTEXITCODE -ne 0) { throw 'Raven native custom-class control build failed.' }
$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'OFFLINE_RAVEN_NATIVE_CUSTOM_CLASS_CONTROL_BUILT' -or
    [string]$proof.source_sha256 -ne $expectedMap -or
    [string]$proof.marker_type_before -ne 'DockPoint' -or
    [string]$proof.marker_type_after -ne 'CompletionistRaven' -or
    $proof.dedicated_showmarker_call_preserved -ne $true -or
    $proof.native_marker_identity_unchanged -ne $true -or
    $proof.native_coordinates_graph_unchanged -ne $true -or
    $proof.bytes_outside_bridge_unchanged -ne $true -or
    $proof.game_files_written -ne $false) {
    throw 'Custom-class offline proof failed validation.'
}
$after = Hash-File $candidate
if ($after -ne ([string]$proof.candidate_sha256).ToLowerInvariant()) {
    throw 'Custom-class candidate hash mismatch.'
}

$manifest = [ordered]@{
    kind = 'completionist-v104-raven-native-custom-class-control'
    marker = 'Completionist_V103_Veithurgard_Raven_01'
    marker_type_before = 'DockPoint'
    marker_type_after = 'CompletionistRaven'
    map_before_sha256 = $expectedMap
    map_after_sha256 = $after
    backup = $backup
    candidate = $candidate
    report = $report
    native_data_ab_manifest = $installedAB[0]
    mapcoords_sha256 = $expectedCoords
    compassgraph_sha256 = $expectedGraph
    wad_r_perm_sha256 = $expectedPerm
    r_ui_wad_sha256 = $expectedWad
    only_mapmenu_written = $true
    saves_progression_marker_state_written = $false
    installed_utc = [DateTime]::UtcNow.ToString('o')
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

try {
    Copy-Item -LiteralPath $candidate -Destination $mapTarget -Force
    if ((Hash-File $mapTarget) -ne $after) { throw 'Installed custom-class mapmenu hash mismatch.' }
} catch {
    Copy-Item -LiteralPath $backup -Destination $mapTarget -Force
    if ((Hash-File $mapTarget) -ne $expectedMap) { throw 'Custom-class install failed and rollback verification also failed.' }
    Remove-Item -LiteralPath $manifestPath -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host ''
Write-Host 'Raven native CUSTOM CLASS A/B control installed.'
Write-Host '- native coordinates + compassgraph: proven working A/B preserved'
Write-Host '- marker ID: unchanged'
Write-Host '- markerType only: DockPoint -> CompletionistRaven'
Write-Host '- dedicated Raven HUD WAD/DCB already installed and hash-verified'
Write-Host '- game file changed by this control: mapmenu.lua only'
Write-Host '- saves/progression/marker state touched: false'
Write-Host ''
Write-Host 'Launch God of War and track the same Raven.'
Write-Host 'Expected: native route/pathfinding remains, HUD art changes from DockPoint to Raven.'
Write-Host 'Current CompletionistRaven in-world resource still points to DockPoint; Raven-specific in-world art is a later isolated step.'
Write-Host ''
Write-Host ("Rollback this class-only control: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
