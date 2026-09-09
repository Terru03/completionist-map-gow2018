param(
    [ValidateSet('Install', 'Remove')][string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before installing or removing the Raven native route re-proof.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$mapTarget = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$bridge = Join-Path (Split-Path $PSScriptRoot -Parent) 'v0.10.3\native-raven-production.lua'
$stateDir = Join-Path $repo 'build\v0.10.4-raven-native-route-reproof'
$backup = Join-Path $stateDir 'mapmenu-before.lua'
$candidate = Join-Path $stateDir 'mapmenu-native-route-reproof.lua'
$manifestPath = Join-Path $stateDir 'active.json'
$sideManifest = Join-Path $repo 'build\v0.10.4-raven-native-side-control\active.json'
$expectedBaseline = 'fb68996fad866acb978d6743b5d6054d0f2a82dba485a307ee810fc100c2be45'
$utf8 = New-Object Text.UTF8Encoding($false)

function Hash-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

if (-not (Test-Path -LiteralPath $mapTarget -PathType Leaf)) { throw "Missing installed mapmenu override: $mapTarget" }

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Raven native route re-proof is already removed.'
        return
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $before = ([string]$manifest.map_before_sha256).ToLowerInvariant()
    $after = ([string]$manifest.map_after_sha256).ToLowerInvariant()
    $current = Hash-File $mapTarget
    if ($current -ne $after -and $current -ne $before) {
        throw 'mapmenu.lua changed after route re-proof install. Refusing automatic overwrite.'
    }
    if ((Hash-File $backup) -ne $before) { throw 'Route re-proof backup hash mismatch.' }
    if ($current -eq $after) {
        Copy-Item -LiteralPath $backup -Destination $mapTarget -Force
    }
    if ((Hash-File $mapTarget) -ne $before) { throw 'Route re-proof rollback hash mismatch.' }
    $removed = Join-Path $stateDir ('removed-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Raven native route re-proof removed. mapmenu.lua restored byte-for-byte.'
    Write-Host '- WAD/DCB files touched: false'
    Write-Host '- saves/progression/marker state touched: false'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Raven native route re-proof is already installed.'
}
if (Test-Path -LiteralPath $sideManifest -PathType Leaf) {
    throw ('Raven SIDE A/B control is still active. Remove it first with:' + [Environment]::NewLine +
        'powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\v0.10.4\install-raven-native-side-control.ps1" -Mode Remove')
}
if (-not (Test-Path -LiteralPath $bridge -PathType Leaf)) { throw "Missing native bridge: $bridge" }

$before = Hash-File $mapTarget
if ($before -ne $expectedBaseline) {
    throw "mapmenu.lua is not the inspected pre-SIDE baseline. Expected $expectedBaseline, got $before. Refusing to stack another runtime patch."
}

$source = [IO.File]::ReadAllText($mapTarget)
$bridgeText = [IO.File]::ReadAllText($bridge)

# This exact fb68996... baseline is the post-v0.10.4 installed mapmenu used by the
# SIDE A/B control. It intentionally does NOT contain the old appended v0.10.3
# native bridge or the old mapmenu-side R3/L3 proof helpers. Validate the actual
# stock-path contract that the re-proof needs instead of requiring stale symbols.
foreach ($needle in @(
    'function MapOn:ShowOnCompass(currState)',
    'game.Compass.ShowMarker(self.currMarkerID, markerType)',
    'CompletionistMapV100_IsRavenCollected',
    'enabledShowOnCompassMarkerFlags',
    'completionistMapV100Selected',
    'Completionist_V103_Veithurgard_Raven_01'
)) {
    if (-not $source.Contains($needle)) { throw "Expected inspected stock-path baseline signature missing: $needle" }
}
if ($source.Contains('BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE')) {
    throw 'Native Raven production bridge already exists in mapmenu.lua.'
}
foreach ($needle in @(
    'local candidate = "Completionist_V103_Veithurgard_Raven_01"',
    'local markerType = consts.COMPASS_MARKER_TYPE_DOCK_POINT',
    'game.Compass.ShowMarker(candidate, markerType)',
    'LEGACY_R3L3_DISABLED',
    'target.active = false',
    'calls_on_load=false'
)) {
    if (-not $bridgeText.Contains($needle)) { throw "Native bridge contract changed. Missing: $needle" }
}

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
Copy-Item -LiteralPath $mapTarget -Destination $backup -Force
if ((Hash-File $backup) -ne $before) { throw 'Route re-proof backup verification failed.' }

$patched = $source.TrimEnd("`r", "`n") + "`r`n" + $bridgeText.TrimEnd("`r", "`n") + "`r`n"
[IO.File]::WriteAllText($candidate, $patched, $utf8)
$after = Hash-File $candidate
if ($after -eq $before) { throw 'Route re-proof candidate did not change mapmenu.lua.' }

$proofText = [IO.File]::ReadAllText($candidate)
if (($proofText.Split('BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE').Count - 1) -ne 1) {
    throw 'Route re-proof candidate does not contain exactly one native Raven bridge.'
}
if (($proofText.Split('game.Compass.ShowMarker(candidate, markerType)').Count - 1) -ne 1) {
    throw 'Route re-proof candidate does not contain exactly one dedicated Raven native ShowMarker call.'
}
if (-not $proofText.Contains('LEGACY_R3L3_DISABLED') -or -not $proofText.Contains('target.active = false')) {
    throw 'Route re-proof candidate lost the runtime legacy-Raven-HUD suppression contract.'
}

$manifest = [ordered]@{
    kind = 'completionist-v104-raven-native-route-reproof'
    marker = 'Completionist_V103_Veithurgard_Raven_01'
    marker_id_hex = 'E15E6BC82AE2773E'
    compass_type = 'DockPoint'
    map_before_sha256 = $before
    map_after_sha256 = $after
    backup = $backup
    candidate = $candidate
    bridge = $bridge
    source_baseline = 'post-v0.10.4-pre-SIDE-stock-ShowOnCompass'
    source_contains_old_fake_hud_helpers = $false
    legacy_r3l3_runtime_suppressed_if_present = $true
    dedicated_native_showmarker_call = $true
    wad_files_written = $false
    dcb_files_written = $false
    save_progression_marker_state_written = $false
    installed_utc = [DateTime]::UtcNow.ToString('o')
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

try {
    Copy-Item -LiteralPath $candidate -Destination $mapTarget -Force
    if ((Hash-File $mapTarget) -ne $after) { throw 'Installed route re-proof hash mismatch.' }
} catch {
    Copy-Item -LiteralPath $backup -Destination $mapTarget -Force
    if ((Hash-File $mapTarget) -ne $before) { throw 'Route re-proof install failed and rollback verification also failed.' }
    Remove-Item -LiteralPath $manifestPath -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host ''
Write-Host 'Raven NATIVE route re-proof installed.'
Write-Host '- exact inspected pre-SIDE stock ShowOnCompass baseline verified'
Write-Host '- Raven selection is intercepted by the appended proven native bridge'
Write-Host '- game.Compass.ShowMarker(candidate, DockPoint) is used'
Write-Host '- any legacy CompletionistMapV100Target Raven HUD is forced inactive while native tracking is active'
Write-Host '- R3_L3 fake marker should NOT render for the Raven'
Write-Host '- same native Raven mapmaster/mapcoords/compassgraph data: unchanged'
Write-Host '- custom Raven WAD/DCB pair: left untouched'
Write-Host '- saves/progression/marker state touched by installer: false'
Write-Host ''
Write-Host 'Launch God of War, select the same Raven, then Add to Compass.'
Write-Host 'Expected control result: STOCK DockPoint native icon, game-owned distance, in-world marker, and native route behavior.'
Write-Host 'If you still see the L3/R3 surrogate, stop and report it; do not stack another patch.'
Write-Host ''
Write-Host 'After testing, close God of War. Do not remove this re-proof until the result/log is collected.'
Write-Host ("Rollback later: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
