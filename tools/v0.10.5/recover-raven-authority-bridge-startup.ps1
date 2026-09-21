param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$Launch
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Owner = 'completionist-map-raven-authority-bridge'
$Schema = 3
$TargetRelative = 'dxgi.dll'
$ProxyContract = 'system32-dxgi-v1'
$KnownBadDxgiHash = '2e93c9c711a5c0f622a4b977b4c8f3e4bc81f0e5b1a8640eb2946830d3d2bd2a'

function Get-LowerHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }).Count -gt 0) {
    throw 'Close God of War and any GoW error dialog first.'
}

$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }

$rollback = Join-Path $repo 'tools\v0.10.5\rollback-raven-authority-bridge.ps1'
$game = [IO.Path]::GetFullPath($GameRoot)
$exe = Join-Path $game 'GoW.exe'
$version = Join-Path $game 'version.dll'
$dxgi = Join-Path $game $TargetRelative
$manifest = Join-Path $game 'mods\completionist-map\native\raven-native-bridge-manifest.json'

foreach ($path in @($exe, $version, $rollback)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required recovery file missing: $path" }
}

$versionBefore = Get-LowerHash $version
$removedLegacyBadDxgi = $false
$ownedRollbacks = 0

for ($depth = 0; $depth -lt 16 -and (Test-Path -LiteralPath $manifest -PathType Leaf); $depth++) {
    $owned = Get-Content -Raw -LiteralPath $manifest | ConvertFrom-Json

    if ($owned.schema -eq 1 -and
        $owned.owner -eq $Owner -and
        $owned.target_relative -eq $TargetRelative) {
        if (-not (Test-Path -LiteralPath $dxgi -PathType Leaf)) {
            Remove-Item -LiteralPath $manifest -Force
            break
        }
        if ((Get-LowerHash $dxgi) -ne $KnownBadDxgiHash) {
            throw 'Legacy DXGI manifest points at unknown DLL; refusing recovery.'
        }
        Remove-Item -LiteralPath $dxgi -Force
        Remove-Item -LiteralPath $manifest -Force
        $removedLegacyBadDxgi = $true
        break
    }

    if ($owned.schema -ne $Schema -or
        $owned.owner -ne $Owner -or
        $owned.target_relative -ne $TargetRelative -or
        $owned.proxy_contract -ne $ProxyContract) {
        throw 'Bridge manifest is not recognized schema-3 DXGI ownership; refusing recovery.'
    }

    & $rollback -GameRoot $game
    $ownedRollbacks++
}

if (Test-Path -LiteralPath $manifest -PathType Leaf) {
    throw 'Owned DXGI rollback chain exceeded safety limit.'
}

if (Test-Path -LiteralPath $dxgi -PathType Leaf) {
    $remainingHash = Get-LowerHash $dxgi
    if ($remainingHash -eq $KnownBadDxgiHash) {
        Remove-Item -LiteralPath $dxgi -Force
        $removedLegacyBadDxgi = $true
    } else {
        throw 'Unknown or unowned game-root dxgi.dll remains; refusing launch.'
    }
}

if ((Get-LowerHash $version) -ne $versionBefore) {
    throw 'version.dll changed during recovery.'
}

Write-Host "RAVEN_NATIVE_BRIDGE_STARTUP_RECOVERED owned_dxgi_absent=true manifest_absent=true version_untouched=true removed_legacy_bad_dxgi=$($removedLegacyBadDxgi.ToString().ToLowerInvariant()) dxgi_rollbacks=$ownedRollbacks"

if ($Launch) {
    Write-Host 'Launching GoW without a Completionist Map native bridge...'
    Start-Process -FilePath $exe -WorkingDirectory $game | Out-Null
}
