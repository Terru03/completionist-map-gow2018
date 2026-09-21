param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$Launch
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Owner = 'completionist-map-raven-authority-bridge'
$KnownBadBridgeHash = '2e93c9c711a5c0f622a4b977b4c8f3e4bc81f0e5b1a8640eb2946830d3d2bd2a'

function Get-LowerHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }).Count -gt 0) {
    throw 'Close God of War and any GoW error dialog first.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$exe = Join-Path $game 'GoW.exe'
$version = Join-Path $game 'version.dll'
$dxgi = Join-Path $game 'dxgi.dll'
$manifest = Join-Path $game 'mods\completionist-map\native\raven-native-bridge-manifest.json'

foreach ($p in @($exe, $version)) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Required game file missing: $p" }
}

$versionBefore = Get-LowerHash $version
$removedDxgi = $false
$removedManifest = $false

$manifestObj = $null
if (Test-Path -LiteralPath $manifest -PathType Leaf) {
    try { $manifestObj = Get-Content -Raw -LiteralPath $manifest | ConvertFrom-Json }
    catch { throw "Bridge manifest exists but is unreadable; refusing cleanup: $manifest" }

    if ($manifestObj.schema -ne 1 -or $manifestObj.owner -ne $Owner -or
        $manifestObj.target_relative -ne 'dxgi.dll') {
        throw 'Bridge manifest is not a recognized Completionist Map manifest; refusing cleanup.'
    }
}

if (Test-Path -LiteralPath $dxgi -PathType Leaf) {
    $dxgiHash = Get-LowerHash $dxgi
    $manifestOwns = $false
    if ($null -ne $manifestObj -and $null -ne $manifestObj.installed_sha256) {
        $manifestOwns = ([string]$manifestObj.installed_sha256).ToLowerInvariant() -eq $dxgiHash
    }

    if (-not $manifestOwns -and $dxgiHash -ne $KnownBadBridgeHash) {
        throw "Unknown dxgi.dll present at game root; refusing delete. sha256=$dxgiHash"
    }

    Remove-Item -LiteralPath $dxgi -Force
    $removedDxgi = $true
}

if ($null -ne $manifestObj) {
    $manifestHash = if ($null -ne $manifestObj.installed_sha256) {
        ([string]$manifestObj.installed_sha256).ToLowerInvariant()
    } else { '' }

    if ($manifestHash -eq $KnownBadBridgeHash -or $removedDxgi -or -not (Test-Path -LiteralPath $dxgi -PathType Leaf)) {
        Remove-Item -LiteralPath $manifest -Force
        $removedManifest = $true
    }
}

# Remove only abandoned Completionist Map temp copies whose content is the exact known bridge.
Get-ChildItem -LiteralPath $game -Filter 'dxgi.dll.completionist-*.tmp' -File -ErrorAction SilentlyContinue |
    ForEach-Object {
        if ((Get-LowerHash $_.FullName) -eq $KnownBadBridgeHash) {
            Remove-Item -LiteralPath $_.FullName -Force
        }
    }

if (Test-Path -LiteralPath $dxgi -PathType Leaf) {
    throw 'A game-root dxgi.dll still exists after cleanup; refusing launch.'
}
if (Test-Path -LiteralPath $manifest -PathType Leaf) {
    throw 'Completionist Map Raven bridge manifest still exists after cleanup; refusing launch.'
}

$versionAfter = Get-LowerHash $version
if ($versionAfter -ne $versionBefore) {
    throw 'version.dll changed during recovery.'
}

Write-Host "RAVEN_NATIVE_BRIDGE_STARTUP_RECOVERED dxgi_absent=true manifest_absent=true version_untouched=true removed_dxgi=$($removedDxgi.ToString().ToLowerInvariant()) removed_manifest=$($removedManifest.ToString().ToLowerInvariant())"

if ($Launch) {
    Write-Host 'Launching GoW without the Completionist Map DXGI bridge...'
    Start-Process -FilePath $exe -WorkingDirectory $game | Out-Null
}
