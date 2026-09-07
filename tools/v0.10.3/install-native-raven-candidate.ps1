param(
    [ValidateSet('Install', 'Remove')][string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
$allowedBranches = @('feat/v0.10.3-native-raven', 'feat/v0.10.4-all-ravens')
if ($branch -notin $allowedBranches) {
    throw "Expected one of [$($allowedBranches -join ', ')], got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before installing or removing the v0.10.3 native Raven candidate.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$mapTarget = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$ravenTarget = Join-Path $game 'mods\lua\gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
$stateDir = Join-Path $repo 'build\v0.10.3-native-raven-candidate'
$manifestPath = Join-Path $stateDir 'active.json'
$mapBackup = Join-Path $stateDir 'mapmenu-before.lua'
$ravenBackup = Join-Path $stateDir 'precisionchallenge-before.lua'
$dcbTool = Join-Path $PSScriptRoot 'native-raven-dcb-install.ps1'
$mapBridge = Join-Path $PSScriptRoot 'native-raven-production.lua'
$lifecycleBridge = Join-Path $PSScriptRoot 'native-raven-lifecycle.lua'
$utf8 = New-Object Text.UTF8Encoding($false)

$researchManifests = @(
    (Join-Path $repo 'build\v0.10.3-native-show\active.json'),
    (Join-Path $repo 'build\v0.10.3-native-runtime\active.json'),
    (Join-Path $repo 'build\v0.10.3-lookup\active.json')
)

function Hash-File([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Restore-TextFile([string]$Target, [string]$Backup, [string]$Before, [string]$After) {
    if (-not (Test-Path -LiteralPath $Backup -PathType Leaf)) { throw "Missing backup: $Backup" }
    $current = Hash-File $Target
    if ($current -ne $After -and $current -ne $Before) {
        throw "$Target changed after candidate install. Refusing automatic overwrite."
    }
    if ($current -ne $Before) {
        Copy-Item -LiteralPath $Backup -Destination $Target -Force
    }
    if ((Hash-File $Target) -ne $Before) { throw "Rollback hash mismatch: $Target" }
}

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'v0.10.3 native Raven candidate is already removed.'
        & $dcbTool -Mode Remove -GameRoot $game
        return
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    Restore-TextFile $mapTarget $mapBackup ([string]$manifest.map_before) ([string]$manifest.map_after)
    Restore-TextFile $ravenTarget $ravenBackup ([string]$manifest.raven_before) ([string]$manifest.raven_after)
    & $dcbTool -Mode Remove -GameRoot $game

    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'v0.10.3 native Raven candidate removed.'
    Write-Host 'Original map/raven Lua overrides and all three stock DCBs were restored.'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'v0.10.3 native Raven candidate is already installed.'
}
foreach ($probeManifest in $researchManifests) {
    if (Test-Path -LiteralPath $probeManifest -PathType Leaf) {
        throw "A research probe is still active: $probeManifest. Roll it back before installing the candidate."
    }
}
foreach ($path in @($mapTarget, $ravenTarget,$dcbTool,$mapBridge,$lifecycleBridge)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing required file: $path" }
}

$mapSource = [IO.File]::ReadAllText($mapTarget)
$ravenSource = [IO.File]::ReadAllText($ravenTarget)
if (-not $mapSource.Contains('[CompletionistMap v0.10.1] MAP_SCRIPT_LOADED')) {
    throw 'Expected tested Completionist map override was not found.'
}
if (-not $mapSource.Contains('function MapOn:ShowOnCompass(currState)')) {
    throw 'MapOn:ShowOnCompass missing from installed override.'
}
if ($mapSource.Contains('BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE')) {
    throw 'Native Raven production bridge already appears in mapmenu.lua.'
}
if (-not $ravenSource.Contains('[CompletionistMap v0.10.1] RAVEN_STATE') -or
    -not $ravenSource.Contains('CompletionistMapV100_IsTargetRaven')) {
    throw 'Expected tested v0.10.1 Raven lifecycle bridge was not found.'
}
if ($ravenSource.Contains('BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN LIFECYCLE BRIDGE')) {
    throw 'Native Raven lifecycle bridge already appears in precisionchallenge.lua.'
}

Write-Host 'Installing authored native Raven DCB data...'
& $dcbTool -Mode Install -GameRoot $game

try {
    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
    $mapBefore = Hash-File $mapTarget
    $ravenBefore = Hash-File $ravenTarget
    Copy-Item -LiteralPath $mapTarget -Destination $mapBackup -Force
    Copy-Item -LiteralPath $ravenTarget -Destination $ravenBackup -Force
    if ((Hash-File $mapBackup) -ne $mapBefore) { throw 'mapmenu backup hash mismatch.' }
    if ((Hash-File $ravenBackup) -ne $ravenBefore) { throw 'precisionchallenge backup hash mismatch.' }

    $mapPatch = [IO.File]::ReadAllText($mapBridge)
    $ravenPatch = [IO.File]::ReadAllText($lifecycleBridge)
    $patchedMap = $mapSource + "`r`n" + $mapPatch + "`r`n"
    $patchedRaven = $ravenSource + "`r`n" + $ravenPatch + "`r`n"

    [IO.File]::WriteAllText($mapTarget, $patchedMap, $utf8)
    [IO.File]::WriteAllText($ravenTarget, $patchedRaven, $utf8)
    $mapAfter = Hash-File $mapTarget
    $ravenAfter = Hash-File $ravenTarget
    if ($mapAfter -eq $mapBefore) { throw 'mapmenu.lua was not patched.' }
    if ($ravenAfter -eq $ravenBefore) { throw 'precisionchallenge.lua was not patched.' }

    $manifest = [ordered]@{
        candidate = 'Completionist_V103_Veithurgard_Raven_01'
        candidate_hash = 'E15E6BC82AE2773E'
        map_before = $mapBefore
        map_after = $mapAfter
        raven_before = $ravenBefore
        raven_after = $ravenAfter
        calls_show_on_install = $false
        legacy_r3l3_for_raven = $false
        installed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 4), $utf8)
} catch {
    try {
        if (Test-Path -LiteralPath $mapBackup -PathType Leaf) { Copy-Item -LiteralPath $mapBackup -Destination $mapTarget -Force }
        if (Test-Path -LiteralPath $ravenBackup -PathType Leaf) { Copy-Item -LiteralPath $ravenBackup -Destination $ravenTarget -Force }
        & $dcbTool -Mode Remove -GameRoot $game
    } catch {
        Write-Warning "Automatic recovery also failed: $($_.Exception.Message)"
    }
    throw
}

Write-Host ''
Write-Host 'Completionist Map v0.10.3 NATIVE RAVEN candidate installed.'
Write-Host '- dedicated authored Raven marker is loaded natively'
Write-Host '- Raven Add/Remove/Replace in Compass uses game.Compass.ShowMarker/HideMarker'
Write-Host '- old direct-XYZ R3/L3 carrier is suppressed whenever Raven native tracking is active'
Write-Host '- target Raven death/restored-killed state hides only the dedicated Raven native marker'
Write-Host '- installer itself does not call ShowMarker and does not change marker progression state'
Write-Host '- tracking is intentionally not auto-restored after a full process restart yet'
Write-Host ''
Write-Host 'Launch the game yourself. For route validation, track the Raven and then move far enough away/around geometry that a straight bearing and a route-aware bearing can diverge.'
Write-Host ("Rollback: powershell -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
