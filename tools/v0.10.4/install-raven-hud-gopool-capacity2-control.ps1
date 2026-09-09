param(
    [ValidateSet('Install','Remove')]
    [string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/v104-raven-hud-research'
$ExpectedUiBefore = '40eb9f6fc934b0fb34b568a3fa74bac24b19e6259b2dc5749f26a8cd90865d36'
$ExpectedUiWad = '5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60'
$ExpectedPermCustomCarrier = '85d33925a10a6d70629a79eb19c51c4c92957f9eb78eda0c1145e585ea5781a5'
$ExpectedCoords = '945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb'
$ExpectedGraph = 'd0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68'
$HudHash = '45E5C7943749F81C'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$StateDir = Join-Path $RepoRoot 'build\v0.10.4-raven-hud-gopool-capacity2-control'
$Candidate = Join-Path $StateDir 'candidate\wad_r_ui.dcb'
$Report = Join-Path $StateDir 'offline-report.json'
$RuntimeDir = Join-Path $StateDir 'runtime'
$ManifestPath = Join-Path $RuntimeDir 'active.json'
$BackupPath = Join-Path $RuntimeDir 'wad_r_ui.dcb.capacity1.before'
$Builder = Join-Path $PSScriptRoot 'build-raven-hud-gopool-capacity2-control.py'

$UiDcb = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_ui.dcb'
$UiWad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
$Perm = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_perm.dcb'
$Coords = Join-Path $GameRoot 'exec\dc\pc_le\mapcoords.dcb'
$Graph = Join-Path $GameRoot 'exec\dc\pc_le\compassgraph.dcb'
$MapMenu = Join-Path $GameRoot 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'

$CarrierManifest = Join-Path $RepoRoot 'build\v0.10.4-raven-inworld-carrier\runtime\active.json'
$StockArtManifest = Join-Path $RepoRoot 'build\v0.10.4-raven-inworld-carrier-stock-art-control\runtime\active.json'
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
    if ($running.Count -gt 0) { throw 'God of War is running. Close it before changing wad_r_ui.dcb.' }
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

function Assert-ProvenCustomCarrierState {
    if ((Get-Sha256 $Perm) -ne $ExpectedPermCustomCarrier) {
        throw "wad_r_perm.dcb is not the custom-art Raven in-world carrier. Remove the stock-art control first."
    }
    if ((Get-Sha256 $UiWad) -ne $ExpectedUiWad) { throw 'r_ui.wad is not the proven custom Raven HUD WAD.' }
    if ((Get-Sha256 $Coords) -ne $ExpectedCoords) { throw 'mapcoords.dcb is not the proven Raven native-routing file.' }
    if ((Get-Sha256 $Graph) -ne $ExpectedGraph) { throw 'compassgraph.dcb is not the proven Raven native-routing file.' }
    if (Test-Path -LiteralPath $StockArtManifest -PathType Leaf) {
        throw 'Raven in-world stock-art control is still active. Remove it before testing GOPool capacity 2.'
    }
    foreach ($p in @($CarrierManifest, $SingleActiveManifest, $CustomClassManifest, $GopoolManifest)) {
        if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Required active manifest missing: $p" }
    }
    $carrier = Get-Content -LiteralPath $CarrierManifest -Raw | ConvertFrom-Json
    if ([string]$carrier.kind -ne 'completionist-v104-raven-inworld-carrier-runtime' -or $carrier.schema -ne 1 -or
        ([string]$carrier.wad_r_perm_after_sha256).ToLowerInvariant() -ne $ExpectedPermCustomCarrier) {
        throw 'Underlying Raven in-world custom carrier manifest is not the expected active candidate.'
    }
    $single = Get-Content -LiteralPath $SingleActiveManifest -Raw | ConvertFrom-Json
    if ([string]$single.kind -ne 'completionist-v104-raven-single-active-compass-control' -or $single.schema -ne 3) {
        throw 'Raven single-target control is not the proven schema-3 version.'
    }
    if ((Get-Sha256 $MapMenu) -ne ([string]$single.map_after_sha256).ToLowerInvariant()) {
        throw 'mapmenu.lua does not match the proven schema-3 Raven control.'
    }
    $gop = Get-Content -LiteralPath $GopoolManifest -Raw | ConvertFrom-Json
    if ($gop.schema -ne 1 -or [string]$gop.operation -ne 'raven_compass_hud_gopool_registration' -or
        ([string]$gop.after_dcb_sha).ToLowerInvariant() -ne $ExpectedUiBefore -or $gop.hud_capacity -ne 1) {
        throw 'Underlying Raven HUD GOPool registration manifest is not the proven capacity-1 state.'
    }
}

Assert-GameClosed
Assert-Branch
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        Write-Host 'Raven HUD GOPool capacity-2 control is already removed.'
        exit 0
    }
    if (-not (Test-Path -LiteralPath $BackupPath -PathType Leaf)) {
        throw "Capacity-2 control backup missing: $BackupPath"
    }
    $m = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    if ([string]$m.kind -ne 'completionist-v104-raven-hud-gopool-capacity2-control' -or $m.schema -ne 1) {
        throw 'Unexpected capacity-2 control manifest.'
    }
    if ((Get-Sha256 $BackupPath) -ne $ExpectedUiBefore) { throw 'Capacity-1 backup hash mismatch.' }
    $after = ([string]$m.wad_r_ui_after_sha256).ToLowerInvariant()
    $live = Get-Sha256 $UiDcb
    if ($live -ne $after -and $live -ne $ExpectedUiBefore) {
        throw "wad_r_ui.dcb is neither capacity-2 control nor capacity-1 baseline: $live"
    }
    if ($live -eq $after) { Copy-Item -LiteralPath $BackupPath -Destination $UiDcb -Force }
    if ((Get-Sha256 $UiDcb) -ne $ExpectedUiBefore) { throw 'Capacity-2 rollback verification failed.' }
    $removed = Join-Path $RuntimeDir ('removed-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '.json')
    Move-Item -LiteralPath $ManifestPath -Destination $removed -Force
    Write-Host 'RAVEN_HUD_GOPOOL_CAPACITY2_CONTROL_REMOVED'
    Write-Host "  wad_r_ui.dcb restored: $ExpectedUiBefore"
    Write-Host '  wad_r_perm / r_ui.wad / mapmenu / mapcoords / compassgraph touched: false'
    exit 0
}

if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {
    throw "Raven HUD GOPool capacity-2 control already active: $ManifestPath"
}
Assert-ProvenCustomCarrierState
if ((Get-Sha256 $UiDcb) -ne $ExpectedUiBefore) {
    throw "wad_r_ui.dcb is not the proven capacity-1 baseline: $(Get-Sha256 $UiDcb)"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }
if (-not (Test-Path -LiteralPath $Builder -PathType Leaf)) { throw "Missing builder: $Builder" }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Candidate) | Out-Null

& $python.Source $Builder --game-root $GameRoot --output $Candidate --report $Report
if ($LASTEXITCODE -ne 0) { throw 'Offline GOPool capacity-2 build failed.' }
$proof = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'OFFLINE_RAVEN_HUD_GOPOOL_CAPACITY2_CONTROL_BUILT' -or
    ([string]$proof.source_sha256).ToLowerInvariant() -ne $ExpectedUiBefore -or
    ([string]$proof.hud_hash).ToUpperInvariant() -ne $HudHash -or
    $proof.hud_index -ne 256 -or $proof.capacity_before -ne 1 -or $proof.capacity_after -ne 2 -or
    $proof.stock_dock_capacity -ne 2 -or $proof.gopool_count_unchanged -ne $true -or
    $proof.only_capacity_low_byte_changed -ne $true -or
    $proof.all_other_gopool_rows_byte_identical -ne $true -or
    $proof.non_data_chunks_byte_identical -ne $true -or $proof.game_files_written -ne $false) {
    throw 'Offline GOPool capacity-2 A/B contract failed.'
}
$candidateSha = ([string]$proof.candidate_sha256).ToLowerInvariant()
if ((Get-Sha256 $Candidate) -ne $candidateSha) { throw 'Capacity-2 candidate hash mismatch.' }
if ((Get-Sha256 $UiDcb) -ne $ExpectedUiBefore) { throw 'Live wad_r_ui.dcb changed during offline build.' }

Copy-Item -LiteralPath $UiDcb -Destination $BackupPath -Force
if ((Get-Sha256 $BackupPath) -ne $ExpectedUiBefore) { throw 'Exact capacity-1 backup verification failed.' }

$m = [ordered]@{
    kind = 'completionist-v104-raven-hud-gopool-capacity2-control'
    schema = 1
    purpose = 'Causal A/B: allow two simultaneous goCompletionistRavenHUD instances for compass HUD plus in-world carrier.'
    installed_utc = [DateTime]::UtcNow.ToString('o')
    wad_r_ui_before_sha256 = $ExpectedUiBefore
    wad_r_ui_after_sha256 = $candidateSha
    hud_hash = $HudHash
    hud_index = 256
    capacity_before = 1
    capacity_after = 2
    only_game_file_written = 'exec/dc/pc_le/wad_r_ui.dcb'
    underlying_gopool_manifest = $GopoolManifest
    inworld_carrier_manifest = $CarrierManifest
    backup = $BackupPath
    candidate = $Candidate
    report = $Report
    saves_progression_marker_state_touched = $false
}
Write-JsonFile $m $ManifestPath

try {
    Copy-Item -LiteralPath $Candidate -Destination $UiDcb -Force
    if ((Get-Sha256 $UiDcb) -ne $candidateSha) { throw 'Installed capacity-2 DCB hash mismatch.' }
    Assert-ProvenCustomCarrierState
} catch {
    Copy-Item -LiteralPath $BackupPath -Destination $UiDcb -Force
    if ((Get-Sha256 $UiDcb) -ne $ExpectedUiBefore) { throw 'Install failed and capacity-1 rollback also failed.' }
    Remove-Item -LiteralPath $ManifestPath -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host ''
Write-Host 'RAVEN_HUD_GOPOOL_CAPACITY2_CONTROL_INSTALLED'
Write-Host "  wad_r_ui.dcb: $ExpectedUiBefore -> $candidateSha"
Write-Host "  goCompletionistRavenHUD $HudHash index 256 capacity: 1 -> 2"
Write-Host '  all other GOPool rows byte-identical: true'
Write-Host '  custom Raven in-world carrier preserved: true'
Write-Host '  wad_r_perm / r_ui.wad / mapmenu / mapcoords / compassgraph touched: false'
Write-Host '  saves/progression/marker state touched: false'
Write-Host ''
Write-Host 'Runtime interpretation:'
Write-Host '  RAVEN appears in-world => capacity 1 was the blocker for the second simultaneous Raven HUD instance.'
Write-Host '  STILL NO marker => custom HUD resource is incompatible with the in-world render path for another reason.'
Write-Host ''
Write-Host ("Rollback: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
