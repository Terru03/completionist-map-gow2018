param(
    [string]$GameRootFixture = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
$installer = Join-Path $repo 'tools\v0.10.5\install-raven-authority-bridge.ps1'
$rollback = Join-Path $repo 'tools\v0.10.5\rollback-raven-authority-bridge.ps1'
$recovery = Join-Path $repo 'tools\v0.10.5\recover-raven-authority-bridge-startup.ps1'
$bridge = Join-Path $repo 'build\raven-authority-bridge\Release\XINPUT1_4.dll'
$buildManifest = Join-Path $repo 'build\raven-authority-bridge\bridge-build-manifest.json'
$fixtureExe = Join-Path $GameRootFixture 'GoW.exe'
$fixtureVersion = Join-Path $GameRootFixture 'version.dll'
foreach ($path in @($installer, $rollback, $recovery, $bridge, $buildManifest, $fixtureExe, $fixtureVersion)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Need test file: $path" }
}
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }).Count -gt 0) {
    throw 'Close God of War first.'
}

$tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\', '/')
$testRoot = Join-Path $tempBase ("completionist-raven-bridge-test-" + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $testRoot | Out-Null
try {
    Copy-Item -LiteralPath $fixtureExe -Destination (Join-Path $testRoot 'GoW.exe')
    Copy-Item -LiteralPath $fixtureVersion -Destination (Join-Path $testRoot 'version.dll')
    $versionBefore = (Get-FileHash -LiteralPath (Join-Path $testRoot 'version.dll') -Algorithm SHA256).Hash
    $target = Join-Path $testRoot 'XINPUT1_4.dll'
    $manifest = Join-Path $testRoot 'mods\completionist-map\native\raven-native-bridge-manifest.json'

    & $installer -GameRoot $testRoot -BridgeDll $bridge -BuildManifest $buildManifest
    if (-not (Test-Path -LiteralPath $target -PathType Leaf) -or
        -not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        throw 'Clean install did not write owned pair.'
    }
    & $installer -GameRoot $testRoot -BridgeDll $bridge -BuildManifest $buildManifest
    $second = Get-Content -Raw -LiteralPath $manifest | ConvertFrom-Json
    if ([string]::IsNullOrWhiteSpace([string]$second.backup_relative)) {
        throw 'Upgrade did not record backup.'
    }
    & $rollback -GameRoot $testRoot
    if (-not (Test-Path -LiteralPath $target -PathType Leaf) -or
        -not (Test-Path -LiteralPath $manifest -PathType Leaf)) {
        throw 'Upgrade rollback did not restore old owned pair.'
    }
    & $rollback -GameRoot $testRoot
    if ((Test-Path -LiteralPath $target) -or (Test-Path -LiteralPath $manifest)) {
        throw 'Clean rollback left active owned pair.'
    }

    [IO.File]::WriteAllBytes($target, [byte[]](1,2,3,4))
    $unknownRefused = $false
    try {
        & $installer -GameRoot $testRoot -BridgeDll $bridge -BuildManifest $buildManifest
    } catch {
        $unknownRefused = $true
    }
    if (-not $unknownRefused) { throw 'Unknown XINPUT1_4.dll overwrite was not refused.' }
    Remove-Item -LiteralPath $target -Force

    & $installer -GameRoot $testRoot -BridgeDll $bridge -BuildManifest $buildManifest
    [IO.File]::WriteAllBytes($target, [byte[]](5,6,7,8))
    $tamperRefused = $false
    try {
        & $rollback -GameRoot $testRoot
    } catch {
        $tamperRefused = $true
    }
    if (-not $tamperRefused) { throw 'Tampered installed XINPUT1_4.dll delete was not refused.' }
    Copy-Item -LiteralPath $bridge -Destination $target -Force
    & $rollback -GameRoot $testRoot

    & $installer -GameRoot $testRoot -BridgeDll $bridge -BuildManifest $buildManifest
    & $recovery -GameRoot $testRoot
    if ((Test-Path -LiteralPath $target) -or (Test-Path -LiteralPath $manifest)) {
        throw 'Recovery left active owned XInput pair.'
    }

    $versionAfter = (Get-FileHash -LiteralPath (Join-Path $testRoot 'version.dll') -Algorithm SHA256).Hash
    if ($versionAfter -ne $versionBefore) { throw 'version.dll test fixture changed.' }
    Write-Host 'RAVEN_NATIVE_BRIDGE_INSTALL_TESTS_PASSED target=XINPUT1_4.dll clean=true upgrade=true unknown_refused=true tamper_refused=true recovery=true version_untouched=true'
}
finally {
    $resolved = [IO.Path]::GetFullPath($testRoot)
    if ($resolved.StartsWith($tempBase + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolved -PathType Container)) {
        Remove-Item -LiteralPath $resolved -Recurse -Force
    }
}
