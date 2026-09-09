param(
    [ValidateSet('Install','Remove')]
    [string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/v104-raven-hud-research'
$ExpectedBeforePerm = '7b4ebef237043e97822ffdfc2ba788b0414434514e9ead723622df0fc12a1961'
$ExpectedAfterPerm  = '85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5'
$ExpectedUiDcb = '40eb9f6fc934b0fb34b568a3fa74bac24b19e6259b2dc5749f26a8cd90865d36'
$ExpectedUiWad = '5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60'
$ExpectedCoords = '945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb'
$ExpectedGraph = 'd0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68'
$ExpectedInWorldUid = '21DC5A7D4AD17628'
$ExpectedInWorldName = 'COMPASS_INWORLD_COMPLETIONIST_RAVEN'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$StateDir = Join-Path $RepoRoot 'build\v0.10.4-raven-inworld-carrier'
$OfflineCandidate = Join-Path $StateDir 'offline\wad_r_perm.dcb'
$OfflineReport = Join-Path $StateDir 'offline\inworld-carrier-offline.json'
$RuntimeDir = Join-Path $StateDir 'runtime'
$ManifestPath = Join-Path $RuntimeDir 'active.json'
$BackupPath = Join-Path $RuntimeDir 'wad_r_perm.dcb.before'
$OfflineRunner = Join-Path $PSScriptRoot 'run-raven-inworld-carrier-offline.ps1'

$Perm = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_perm.dcb'
$UiDcb = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_ui.dcb'
$UiWad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
$Coords = Join-Path $GameRoot 'exec\dc\pc_le\mapcoords.dcb'
$Graph = Join-Path $GameRoot 'exec\dc\pc_le\compassgraph.dcb'
$MapMenu = Join-Path $GameRoot 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'

$SingleActiveManifest = Join-Path $RepoRoot 'build\v0.10.4-raven-single-active-compass-control\active.json'
$CustomClassManifest = Join-Path $RepoRoot 'build\v0.10.4-raven-native-custom-class-control\active.json'
$GopoolManifest = Join-Path $RepoRoot 'build\v0.10.4-raven-compass-hud-gopool-registration\active-install.json'

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return ((Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash).ToLowerInvariant()
}

function Assert-GameClosed {
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessName -eq 'GoW' -or $_.ProcessName -eq 'GodOfWar'
    })
    if ($running.Count -gt 0) {
        throw 'God of War is running. Close it before changing wad_r_perm.dcb.'
    }
}

function Assert-Branch {
    $branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) {
        throw "Expected Git branch '$ExpectedBranch', found '$branch'."
    }
}

function Write-JsonFile([object]$Object, [string]$Path) {
    $json = $Object | ConvertTo-Json -Depth 10
    [IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

function Assert-ProvenCompanionState {
    $checks = @(
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
        throw 'Proven schema-3 Raven single-active control is not active.'
    }
    $single = Get-Content -LiteralPath $SingleActiveManifest -Raw | ConvertFrom-Json
    if ([string]$single.kind -ne 'completionist-v104-raven-single-active-compass-control' -or $single.schema -ne 3) {
        throw 'Active Raven single-target manifest is not the proven schema-3 control.'
    }
    if ((Get-Sha256 $MapMenu) -ne ([string]$single.map_after_sha256).ToLowerInvariant()) {
        throw 'Live mapmenu.lua does not match the proven schema-3 single-target control.'
    }

    if (-not (Test-Path -LiteralPath $CustomClassManifest -PathType Leaf)) {
        throw 'CompletionistRaven custom-class control manifest is not active.'
    }
    if (-not (Test-Path -LiteralPath $GopoolManifest -PathType Leaf)) {
        throw 'Raven HUD GOPool registration manifest is not active.'
    }
}

Assert-GameClosed
Assert-Branch
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        Write-Host 'Raven in-world carrier is already removed.'
        exit 0
    }
    if (-not (Test-Path -LiteralPath $BackupPath -PathType Leaf)) {
        throw "Active in-world carrier manifest exists but exact-byte backup is missing: $BackupPath"
    }

    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    if ([string]$manifest.kind -ne 'completionist-v104-raven-inworld-carrier-runtime' -or $manifest.schema -ne 1) {
        throw 'Unexpected Raven in-world carrier manifest.'
    }
    if ((Get-Sha256 $BackupPath) -ne $ExpectedBeforePerm) {
        throw 'Raven in-world carrier backup does not match the proven pre-carrier wad_r_perm.dcb.'
    }

    $live = Get-Sha256 $Perm
    if ($live -ne $ExpectedAfterPerm -and $live -ne $ExpectedBeforePerm) {
        throw "Live wad_r_perm.dcb is neither the installed Raven carrier nor the exact pre-carrier baseline: $live"
    }

    if ($live -eq $ExpectedAfterPerm) {
        Copy-Item -LiteralPath $BackupPath -Destination $Perm -Force
    }
    if ((Get-Sha256 $Perm) -ne $ExpectedBeforePerm) {
        throw 'Raven in-world carrier rollback verification failed.'
    }

    $removedPath = Join-Path $RuntimeDir ('removed-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '.json')
    Move-Item -LiteralPath $ManifestPath -Destination $removedPath -Force

    Write-Host 'RAVEN_INWORLD_CARRIER_REMOVED'
    Write-Host "  wad_r_perm.dcb restored SHA256: $ExpectedBeforePerm"
    Write-Host '  r_ui.wad / wad_r_ui.dcb touched: false'
    Write-Host '  mapmenu / mapcoords / compassgraph touched: false'
    Write-Host '  saves/progression/marker state touched: false'
    exit 0
}

if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {
    throw "Raven in-world carrier is already installed: $ManifestPath"
}

Assert-ProvenCompanionState

$liveBefore = Get-Sha256 $Perm
if ($liveBefore -ne $ExpectedBeforePerm) {
    throw "wad_r_perm.dcb is not the proven pre-carrier baseline. Expected $ExpectedBeforePerm, got $liveBefore"
}

if (-not (Test-Path -LiteralPath $OfflineRunner -PathType Leaf)) {
    throw "Missing offline gate runner: $OfflineRunner"
}

# Rebuild/revalidate from the live proven baseline immediately before install.
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $OfflineRunner -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Raven in-world offline gate failed immediately before install.' }

if ((Get-Sha256 $Perm) -ne $ExpectedBeforePerm) {
    throw 'Live wad_r_perm.dcb changed during the offline gate.'
}
if ((Get-Sha256 $OfflineCandidate) -ne $ExpectedAfterPerm) {
    throw 'Offline Raven in-world candidate hash does not match the pinned runtime candidate.'
}

$proof = Get-Content -LiteralPath $OfflineReport -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'OFFLINE_RAVEN_INWORLD_CARRIER_BUILT' -or
    $proof.ready_for_reversible_runtime_install -ne $true -or
    ([string]$proof.candidate_sha256).ToLowerInvariant() -ne $ExpectedAfterPerm -or
    [string]$proof.new_export.name -ne $ExpectedInWorldName -or
    ([string]$proof.new_export.uid).ToUpperInvariant() -ne $ExpectedInWorldUid -or
    $proof.topology_gates.existing_relocation_semantics_preserved -ne $true -or
    $proof.topology_gates.normalized_candidate_data_equals_source -ne $true) {
    throw 'Pinned Raven in-world candidate contract failed.'
}

Copy-Item -LiteralPath $Perm -Destination $BackupPath -Force
if ((Get-Sha256 $BackupPath) -ne $ExpectedBeforePerm) {
    throw 'Exact pre-carrier wad_r_perm.dcb backup verification failed.'
}

$manifest = [ordered]@{
    kind = 'completionist-v104-raven-inworld-carrier-runtime'
    schema = 1
    purpose = 'Give CompletionistRaven an independent in-world carrier using the custom Raven HUD art while preserving native routing.'
    installed_utc = [DateTime]::UtcNow.ToString('o')
    wad_r_perm_before_sha256 = $ExpectedBeforePerm
    wad_r_perm_after_sha256 = $ExpectedAfterPerm
    new_export = $ExpectedInWorldName
    new_export_uid = $ExpectedInWorldUid
    completionist_raven_inworld_before = '0E24C47DE2F769CA'
    completionist_raven_inworld_after = $ExpectedInWorldUid
    completionist_raven_hud_icon = '45E5C7943749F81C'
    offline_report = $OfflineReport
    offline_candidate = $OfflineCandidate
    backup = $BackupPath
    single_active_manifest = $SingleActiveManifest
    custom_class_manifest = $CustomClassManifest
    gopool_manifest = $GopoolManifest
    only_game_file_written = 'exec/dc/pc_le/wad_r_perm.dcb'
    saves_progression_marker_state_touched = $false
}
Write-JsonFile $manifest $ManifestPath

try {
    Copy-Item -LiteralPath $OfflineCandidate -Destination $Perm -Force
    $installed = Get-Sha256 $Perm
    if ($installed -ne $ExpectedAfterPerm) {
        throw "Installed Raven in-world carrier hash mismatch: $installed"
    }
    Assert-ProvenCompanionState
} catch {
    Copy-Item -LiteralPath $BackupPath -Destination $Perm -Force
    if ((Get-Sha256 $Perm) -ne $ExpectedBeforePerm) {
        throw 'Install failed and exact wad_r_perm rollback also failed.'
    }
    Remove-Item -LiteralPath $ManifestPath -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host ''
Write-Host 'RAVEN_INWORLD_CARRIER_INSTALLED'
Write-Host "  wad_r_perm.dcb: $ExpectedBeforePerm -> $ExpectedAfterPerm"
Write-Host "  new export: $ExpectedInWorldName"
Write-Host "  new UID:    $ExpectedInWorldUid"
Write-Host '  CompletionistRaven in-world carrier: dedicated Raven'
Write-Host '  custom Raven HUD IconName reused: true'
Write-Host '  stock DockPoint resource modified: false'
Write-Host '  r_ui.wad / wad_r_ui.dcb touched: false'
Write-Host '  mapmenu / mapcoords / compassgraph touched: false'
Write-Host '  saves/progression/marker state touched: false'
Write-Host ''
Write-Host 'Launch God of War and track the same Raven.'
Write-Host 'Expected: Raven HUD art + Raven floating in-world art + native distance/pathfinding + stock single-target semantics.'
Write-Host ''
Write-Host ("Rollback: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
