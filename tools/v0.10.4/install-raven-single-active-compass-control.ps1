param(
    [ValidateSet('Install','Remove')]
    [string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/v104-raven-hud-research'
$ExpectedMapBefore = '55e6ab3771417211cab670aaa4871e5f4083dac8f00f324d5584e803bb9a11a9'
$ExpectedPerm = '7b4ebef237043e97822ffdfc2ba788b0414434514e9ead723622df0fc12a1961'
$ExpectedUiDcb = '40eb9f6fc934b0fb34b568a3fa74bac24b19e6259b2dc5749f26a8cd90865d36'
$ExpectedUiWad = '5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60'
$ExpectedCoords = '945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb'
$ExpectedGraph = 'd0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$StateDir = Join-Path $RepoRoot 'build\v0.10.4-raven-single-active-compass-control'
$Candidate = Join-Path $StateDir 'mapmenu-single-active.lua'
$OfflineReport = Join-Path $StateDir 'offline-report.json'
$ManifestPath = Join-Path $StateDir 'active.json'
$BackupPath = Join-Path $StateDir 'mapmenu-before.lua'
$Patcher = Join-Path $PSScriptRoot 'patch-raven-single-active-compass.py'

$MapTarget = Join-Path $GameRoot 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$PermTarget = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_perm.dcb'
$UiDcbTarget = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_ui.dcb'
$UiWadTarget = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
$CoordsTarget = Join-Path $GameRoot 'exec\dc\pc_le\mapcoords.dcb'
$GraphTarget = Join-Path $GameRoot 'exec\dc\pc_le\compassgraph.dcb'

$CustomClassManifest = Join-Path $RepoRoot 'build\v0.10.4-raven-native-custom-class-control\active.json'
$GopoolManifest = Join-Path $RepoRoot 'build\v0.10.4-raven-compass-hud-gopool-registration\active-install.json'
$NativeAbRoot = Join-Path $RepoRoot 'build\v0.10.4\native-raven-no-render\ab-transactions'

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return ((Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant())
}

function Assert-GameClosed {
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessName -eq 'GoW' -or $_.ProcessName -eq 'GodOfWar'
    })
    if ($running.Count -gt 0) { throw 'God of War is running. Close it before changing mapmenu.lua.' }
}

function Assert-Branch {
    $branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) {
        throw "Expected Git branch '$ExpectedBranch', found '$branch'."
    }
}

function Write-JsonFile([object]$Object, [string]$Path) {
    $json = $Object | ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

Assert-GameClosed
Assert-Branch

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        Write-Host 'Raven single-active compass control is already removed.'
        exit 0
    }
    $m = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    if ([string]$m.kind -ne 'completionist-v104-raven-single-active-compass-control') {
        throw 'Unexpected single-active control manifest kind.'
    }
    $live = Get-Sha256 $MapTarget
    $before = ([string]$m.map_before_sha256).ToLowerInvariant()
    $after = ([string]$m.map_after_sha256).ToLowerInvariant()
    if ($live -ne $before -and $live -ne $after) {
        throw "mapmenu.lua changed after install. Expected before/after known state, got $live"
    }
    if ((Get-Sha256 $BackupPath) -ne $before) { throw 'Exact mapmenu backup hash mismatch.' }
    if ($live -eq $after) {
        Copy-Item -LiteralPath $BackupPath -Destination $MapTarget -Force
    }
    if ((Get-Sha256 $MapTarget) -ne $before) { throw 'Single-active rollback verification failed.' }
    $removed = Join-Path $StateDir ('removed-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '.json')
    Move-Item -LiteralPath $ManifestPath -Destination $removed
    Write-Host 'RAVEN_SINGLE_ACTIVE_COMPASS_CONTROL_REMOVED'
    Write-Host '  mapmenu.lua restored byte-for-byte: true'
    Write-Host '  Raven HUD/DCB/native data touched: false'
    exit 0
}

if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {
    throw "Single-active compass control is already installed: $ManifestPath"
}
if (-not (Test-Path -LiteralPath $CustomClassManifest -PathType Leaf)) {
    throw 'Custom CompletionistRaven class control is not active.'
}
if (-not (Test-Path -LiteralPath $GopoolManifest -PathType Leaf)) {
    throw 'Raven HUD GOPool registration is not active.'
}

$installedNativeAb = @()
if (Test-Path -LiteralPath $NativeAbRoot -PathType Container) {
    Get-ChildItem -LiteralPath $NativeAbRoot -Recurse -Filter manifest.json -File | ForEach-Object {
        try {
            $j = Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
            if ([string]$j.kind -eq 'v104-native-raven-coordinate-graph-ab-v1' -and [string]$j.state -eq 'installed') {
                $installedNativeAb += $_.FullName
            }
        } catch {}
    }
}
if ($installedNativeAb.Count -ne 1) {
    throw "Expected exactly one installed Raven mapcoords/compassgraph A/B, found $($installedNativeAb.Count)."
}

$checks = @(
    @($MapTarget, $ExpectedMapBefore, 'mapmenu.lua'),
    @($PermTarget, $ExpectedPerm, 'wad_r_perm.dcb'),
    @($UiDcbTarget, $ExpectedUiDcb, 'wad_r_ui.dcb'),
    @($UiWadTarget, $ExpectedUiWad, 'r_ui.wad'),
    @($CoordsTarget, $ExpectedCoords, 'mapcoords.dcb'),
    @($GraphTarget, $ExpectedGraph, 'compassgraph.dcb')
)
foreach ($row in $checks) {
    $actual = Get-Sha256 $row[0]
    if ($actual -ne $row[1]) {
        throw "$($row[2]) is not the proven Raven HUD/native-routing baseline. Expected $($row[1]), got $actual"
    }
}

if (-not (Test-Path -LiteralPath $Patcher -PathType Leaf)) { throw "Missing patcher: $Patcher" }
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
Copy-Item -LiteralPath $MapTarget -Destination $BackupPath -Force
if ((Get-Sha256 $BackupPath) -ne $ExpectedMapBefore) { throw 'mapmenu backup verification failed.' }

& $python.Source $Patcher --input $MapTarget --output $Candidate --report $OfflineReport
if ($LASTEXITCODE -ne 0) { throw 'Single-active compass candidate build failed.' }
$proof = Get-Content -LiteralPath $OfflineReport -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'OFFLINE_RAVEN_SINGLE_ACTIVE_COMPASS_CONTROL_BUILT' -or
    $proof.schema -ne 3 -or
    $proof.changes.append_only -ne $true -or
    $proof.changes.source_prefix_byte_identical -ne $true -or
    $proof.changes.raven_origin_actions_use_custom_class_manager -ne $true -or
    $proof.changes.raven_remove_is_direct_HideMarker -ne $true -or
    $proof.changes.raven_add_is_direct_ShowMarker_custom_class -ne $true -or
    $proof.changes.stock_origin_action_hides_raven_before_delegate -ne $true -or
    $proof.changes.async_hide_watchdog -ne $true -or
    $proof.changes.prompt_always_live_for_raven -ne $true -or
    $proof.game_files_written -ne $false) {
    throw 'Offline single-active/custom-class-manager proof failed.'
}
$after = Get-Sha256 $Candidate
if ($after -ne ([string]$proof.candidate_sha256).ToLowerInvariant()) {
    throw 'Candidate hash does not match offline report.'
}

$m = [ordered]@{
    kind = 'completionist-v104-raven-single-active-compass-control'
    schema = 3
    purpose = 'Use the live CompletionistRaven manager query for Raven add/remove and preserve stock single-target replacement semantics.'
    map_before_sha256 = $ExpectedMapBefore
    map_after_sha256 = $after
    wad_r_perm_sha256 = $ExpectedPerm
    wad_r_ui_sha256 = $ExpectedUiDcb
    r_ui_wad_sha256 = $ExpectedUiWad
    mapcoords_sha256 = $ExpectedCoords
    compassgraph_sha256 = $ExpectedGraph
    custom_class_manifest = $CustomClassManifest
    gopool_manifest = $GopoolManifest
    native_data_ab_manifest = $installedNativeAb[0]
    backup = $BackupPath
    candidate = $Candidate
    offline_report = $OfflineReport
    only_mapmenu_written = $true
    saves_progression_marker_state_touched = $false
    installed_utc = [DateTime]::UtcNow.ToString('o')
}
Write-JsonFile $m $ManifestPath

try {
    Copy-Item -LiteralPath $Candidate -Destination $MapTarget -Force
    if ((Get-Sha256 $MapTarget) -ne $after) { throw 'Installed mapmenu hash mismatch.' }
} catch {
    Copy-Item -LiteralPath $BackupPath -Destination $MapTarget -Force
    if ((Get-Sha256 $MapTarget) -ne $ExpectedMapBefore) {
        throw 'Install failed and exact rollback verification also failed.'
    }
    Remove-Item -LiteralPath $ManifestPath -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host 'RAVEN_SINGLE_ACTIVE_COMPASS_CONTROL_INSTALLED'
Write-Host "  mapmenu.lua: $ExpectedMapBefore -> $after"
Write-Host '  only mapmenu.lua written: true'
Write-Host '  Raven add/remove now uses live CompletionistRaven manager state: true'
Write-Host '  stock <-> Raven single-target replacement preserved: true'
Write-Host '  Raven prompt derives from live manager state: true'
Write-Host '  Raven HUD + GOPool registration preserved: true'
Write-Host '  native mapcoords/compassgraph preserved: true'
Write-Host '  saves/progression/marker state touched: false'
Write-Host ''
Write-Host 'Runtime test:'
Write-Host '  1) Raven inactive, no stock target => Add to Compass; press => Raven only'
Write-Host '  2) Raven active => text says Remove from Compass; press => nothing tracked'
Write-Host '  3) stock marker active => Raven says Replace in Compass; press => Raven only'
Write-Host '  4) Raven active -> stock marker => stock only'
Write-Host '  5) Raven HUD/distance/native routing remain unchanged'
Write-Host ''
Write-Host ("Rollback: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
