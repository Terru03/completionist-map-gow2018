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
    throw 'Close God of War before installing or removing the Raven native SIDE control.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$mapTarget = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$stateDir = Join-Path $repo 'build\v0.10.4-raven-native-side-control'
$backup = Join-Path $stateDir 'mapmenu-before.lua'
$candidate = Join-Path $stateDir 'mapmenu-side-control.lua'
$report = Join-Path $stateDir 'side-control.json'
$manifestPath = Join-Path $stateDir 'active.json'
$patcher = Join-Path $PSScriptRoot 'patch-raven-native-side-control.py'

function Hash-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

if (-not (Test-Path -LiteralPath $mapTarget -PathType Leaf)) { throw "Missing installed mapmenu override: $mapTarget" }

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Raven native SIDE control is already removed.'
        return
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $before = ([string]$manifest.map_before_sha256).ToLowerInvariant()
    $after = ([string]$manifest.map_after_sha256).ToLowerInvariant()
    $current = Hash-File $mapTarget
    if ($current -ne $after -and $current -ne $before) {
        throw 'mapmenu.lua changed after SIDE control install. Refusing automatic overwrite.'
    }
    if ((Hash-File $backup) -ne $before) { throw 'SIDE control backup hash mismatch.' }
    if ($current -eq $after) {
        Copy-Item -LiteralPath $backup -Destination $mapTarget -Force
    }
    if ((Hash-File $mapTarget) -ne $before) { throw 'SIDE control rollback hash mismatch.' }
    $removed = Join-Path $stateDir ('removed-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Raven native SIDE control removed. mapmenu.lua restored byte-for-byte.'
    Write-Host '- WAD/DCB files touched: false'
    Write-Host '- saves/progression/marker state touched: false'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Raven native SIDE control is already installed.'
}
if (-not (Test-Path -LiteralPath $patcher -PathType Leaf)) { throw "Missing patcher: $patcher" }
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
$before = Hash-File $mapTarget
Copy-Item -LiteralPath $mapTarget -Destination $backup -Force
if ((Hash-File $backup) -ne $before) { throw 'SIDE control backup verification failed.' }

Write-Host 'Building Raven-only stock SIDE control on the installed stock ShowOnCompass path...'
& $python.Source $patcher --input $mapTarget --output $candidate --report $report
if ($LASTEXITCODE -ne 0) { throw 'Raven native SIDE control build failed.' }
$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'OFFLINE_RAVEN_NATIVE_SIDE_CONTROL_BUILT' -or
    [string]$proof.source_sha256 -ne $before -or
    [string]$proof.marker_type_before -ne 'stock_flag_derived' -or
    [string]$proof.marker_type_after -ne 'SIDE' -or
    $proof.source_mapmenu_sha256_pinned -ne $true -or
    $proof.stock_show_call_unchanged -ne $true -or
    $proof.only_guarded_raven_side_override_inserted -ne $true -or
    $proof.source_reconstructs_exactly_after_removing_insertion -ne $true -or
    $proof.game_files_written -ne $false) {
    throw 'SIDE control offline proof failed validation.'
}
$after = Hash-File $candidate
if ($after -ne ([string]$proof.candidate_sha256).ToLowerInvariant()) { throw 'SIDE control candidate hash mismatch.' }

$manifest = [ordered]@{
    kind = 'completionist-v104-raven-native-side-control'
    control_path = 'stock-MapOn-ShowOnCompass-raven-only-override'
    map_before_sha256 = $before
    map_after_sha256 = $after
    backup = $backup
    candidate = $candidate
    marker = 'Completionist_V103_Veithurgard_Raven_01'
    marker_type_before = 'stock_flag_derived'
    marker_type_after = 'SIDE'
    stock_show_call_unchanged = $true
    raven_only_guard = $true
    dcb_files_written = $false
    wad_files_written = $false
    save_progression_marker_state_written = $false
    installed_utc = [DateTime]::UtcNow.ToString('o')
}
$manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

try {
    Copy-Item -LiteralPath $candidate -Destination $mapTarget -Force
    if ((Hash-File $mapTarget) -ne $after) { throw 'Installed SIDE control hash mismatch.' }
} catch {
    Copy-Item -LiteralPath $backup -Destination $mapTarget -Force
    if ((Hash-File $mapTarget) -ne $before) { throw 'SIDE control install failed and rollback verification also failed.' }
    Remove-Item -LiteralPath $manifestPath -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host ''
Write-Host 'Raven native SIDE A/B control installed.'
Write-Host '- actual installed path targeted: stock MapOn:ShowOnCompass'
Write-Host '- exact Raven marker only: true'
Write-Host '- same Raven marker ID: true'
Write-Host '- same mapcoords position: true'
Write-Host '- same compassgraph edge: true'
Write-Host '- stock ShowMarker(self.currMarkerID, markerType) call preserved'
Write-Host '- Raven markerType only: stock flag-derived -> SIDE'
Write-Host '- every non-Raven map marker keeps stock behavior'
Write-Host '- custom Raven WAD/DCB artwork pair left untouched'
Write-Host '- saves/progression/marker state touched: false'
Write-Host ''
Write-Host 'Launch God of War and Add the same Raven to Compass.'
Write-Host 'Observe: routed direction/bends, distance behavior, and an in-world marker.'
Write-Host 'The compass icon should be stock SIDE for this control; that is intentional.'
Write-Host ''
Write-Host 'After the test, close God of War and remove the control with:'
Write-Host ("powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
