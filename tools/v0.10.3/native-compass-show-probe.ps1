param(
    [ValidateSet('Install', 'Remove')][string]$Mode,
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'research/v0.10.3-native-compass') {
    throw "Expected research/v0.10.3-native-compass, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before installing or removing the native compass show probe.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$mapTarget = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$stateDir = Join-Path $repo 'build\v0.10.3-native-show'
$manifestPath = Join-Path $stateDir 'active.json'
$backupPath = Join-Path $stateDir 'mapmenu-before-native-show.lua'
$nativeRuntime = Join-Path $PSScriptRoot 'native-raven-runtime-probe.ps1'
$nativeRuntimeManifest = Join-Path $repo 'build\v0.10.3-native-runtime\active.json'
$lookup = Join-Path $PSScriptRoot 'lookup-probe.ps1'
$lookupManifest = Join-Path $repo 'build\v0.10.3-lookup\active.json'
$probeSource = Join-Path $PSScriptRoot 'native-compass-show-probe.lua'
$utf8 = New-Object Text.UTF8Encoding($false)

function Hash-File([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Restore-MapFromManifest($Manifest) {
    if (-not (Test-Path -LiteralPath $backupPath -PathType Leaf)) {
        throw "Missing mapmenu backup: $backupPath"
    }
    $before = ([string]$Manifest.map_before).ToUpperInvariant()
    $after = ([string]$Manifest.map_after).ToUpperInvariant()
    $current = Hash-File $mapTarget
    if ($current -ne $after -and $current -ne $before) {
        throw 'mapmenu.lua changed after native show probe install. Refusing overwrite.'
    }
    if ($current -ne $before) {
        Copy-Item -LiteralPath $backupPath -Destination $mapTarget -Force
    }
    if ((Hash-File $mapTarget) -ne $before) {
        throw 'mapmenu.lua rollback hash mismatch.'
    }
}

if ($Mode -eq 'Remove') {
    if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        Restore-MapFromManifest $manifest
        $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
        Move-Item -LiteralPath $manifestPath -Destination $removed
        Write-Host 'Native compass show Lua probe removed.'
    } else {
        Write-Host 'Native compass show Lua probe is already removed.'
    }

    if (Test-Path -LiteralPath $nativeRuntimeManifest -PathType Leaf) {
        & $nativeRuntime -Mode Remove -GameRoot $game
        Write-Host 'Native Raven DCB runtime probe removed.'
    } else {
        Write-Host 'Native Raven DCB runtime probe is already removed.'
    }
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Native compass show probe is already active. Remove it first.'
}
if (Test-Path -LiteralPath $nativeRuntimeManifest -PathType Leaf) {
    throw 'A native Raven DCB runtime probe is already active. Remove it first.'
}
if (Test-Path -LiteralPath $lookupManifest -PathType Leaf) {
    throw 'A lookup probe is already active. Remove it first.'
}
if (-not (Test-Path -LiteralPath $mapTarget -PathType Leaf)) {
    throw "Completionist map override missing: $mapTarget"
}
if (-not (Test-Path -LiteralPath $probeSource -PathType Leaf)) {
    throw "Native show Lua source missing: $probeSource"
}

# Install the already-validated authored Raven DCB runtime copies. This also
# installs the read-only lookup probe; we immediately remove only that Lua probe
# so the DCBs remain active while mapmenu returns to the tested v0.10.1 state.
& $nativeRuntime -Mode Install -GameRoot $game
if (-not (Test-Path -LiteralPath $nativeRuntimeManifest -PathType Leaf)) {
    throw 'Native Raven DCB runtime install did not leave an active manifest.'
}

try {
    if (Test-Path -LiteralPath $lookupManifest -PathType Leaf) {
        & $lookup -Mode Remove -GameRoot $game
    }
    if (Test-Path -LiteralPath $lookupManifest -PathType Leaf) {
        throw 'Read-only lookup probe remained active after removal.'
    }

    $source = [IO.File]::ReadAllText($mapTarget)
    if (-not $source.Contains('[CompletionistMap v0.10.1] MAP_SCRIPT_LOADED')) {
        throw 'Expected Completionist v0.10.1 map override not found.'
    }
    if (-not $source.Contains('function MapOn:ShowOnCompass(currState)')) {
        throw 'MapOn:ShowOnCompass missing from installed override.'
    }
    if (-not $source.Contains('CUSTOM_COMPASS')) {
        throw 'Expected existing custom compass prototype is missing.'
    }
    if ($source.Contains('BEGIN COMPLETIONIST V0.10.3 NATIVE COMPASS SHOW PROBE')) {
        throw 'Native compass show probe already appears in mapmenu.lua.'
    }

    New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
    Copy-Item -LiteralPath $mapTarget -Destination $backupPath -Force
    $before = Hash-File $mapTarget
    if ((Hash-File $backupPath) -ne $before) {
        throw 'mapmenu.lua backup hash mismatch.'
    }

    $probe = [IO.File]::ReadAllText($probeSource)
    $patched = $source + "`r`n" + $probe + "`r`n"
    [IO.File]::WriteAllText($mapTarget, $patched, $utf8)
    $after = Hash-File $mapTarget
    if ($after -eq $before) {
        throw 'Native compass show probe did not change mapmenu.lua.'
    }

    $manifest = [ordered]@{
        map_target = $mapTarget
        map_backup = $backupPath
        map_before = $before
        map_after = $after
        candidate = 'Completionist_V103_Veithurgard_Raven_01'
        candidate_hash = 'E15E6BC82AE2773E'
        compass_show_called_on_install = $false
        installed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 4), $utf8)
} catch {
    try {
        if (Test-Path -LiteralPath $backupPath -PathType Leaf) {
            Copy-Item -LiteralPath $backupPath -Destination $mapTarget -Force
        }
        if (Test-Path -LiteralPath $nativeRuntimeManifest -PathType Leaf) {
            & $nativeRuntime -Mode Remove -GameRoot $game
        }
    } catch {
        Write-Warning "Automatic recovery also failed: $($_.Exception.Message)"
    }
    throw
}

Write-Host ''
Write-Host 'v0.10.3 native Raven COMPASS SHOW proof installed.'
Write-Host 'No Compass.ShowMarker call occurs during installation or game startup.'
Write-Host 'The native call happens only if YOU select the synthetic Raven and press Add to Compass.'
Write-Host 'The old R3_L3/manual XYZ HUD target is disabled before the native request.'
Write-Host ''
Write-Host 'TEST:'
Write-Host '1. Launch God of War and load the Veithurgard save.'
Write-Host '2. Open Midgard map and select the Raven.'
Write-Host '3. Press Add to Compass ONCE.'
Write-Host '4. If the game remains stable, close the map and inspect the real HUD compass/distance.'
Write-Host '5. Take a screenshot if a native marker appears. Then fully close the game.'
Write-Host ''
Write-Host 'If the game crashes after Add to Compass, do not retry. Run the collector/rollback after the process is gone.'
Write-Host ("Manual rollback: powershell -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
