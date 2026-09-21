param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Owner = 'completionist-map-raven-authority-bridge'
$Schema = 3
$TargetRelative = 'dxgi.dll'
$ProxyContract = 'system32-dxgi-v1'
$ManifestRelative = 'mods\completionist-map\native\raven-native-bridge-manifest.json'

function Get-LowerHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-ChildPath([string]$Root, [string]$Path) {
    $rootFull = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    $pathFull = [IO.Path]::GetFullPath($Path)
    if (-not $pathFull.StartsWith($rootFull + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Path left game root: $pathFull"
    }
    return $pathFull
}

if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }).Count -gt 0) {
    throw 'Close God of War first.'
}

$operationLibrary = Join-Path $PSScriptRoot 'raven-authority-bridge-operation.ps1'
if (-not (Test-Path -LiteralPath $operationLibrary -PathType Leaf)) {
    throw "Need bridge operation library: $operationLibrary"
}
. $operationLibrary

$game = [IO.Path]::GetFullPath($GameRoot)
$journalPath = Get-RavenBridgeOperationPath $game
if (Test-Path -LiteralPath $journalPath -PathType Leaf) {
    $recovered = Complete-RavenBridgeInterruptedOperation -GameRoot $game
    Write-Host (
        "RAVEN_NATIVE_BRIDGE_ROLLBACK_RECOVERED_INTERRUPTION operation=$($recovered.Operation) " +
        "restored_previous=$($recovered.RestoredPrevious.ToString().ToLowerInvariant())")
    return
}
$target = Assert-ChildPath $game (Join-Path $game $TargetRelative)
$version = Assert-ChildPath $game (Join-Path $game 'version.dll')
$manifestPath = Assert-ChildPath $game (Join-Path $game $ManifestRelative)

foreach ($path in @($target, $manifestPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Need installed bridge file: $path" }
}

$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.schema -ne $Schema -or
    $manifest.owner -ne $Owner -or
    $manifest.target_relative -ne $TargetRelative -or
    $manifest.proxy_contract -ne $ProxyContract) {
    throw 'Bridge manifest not known. Refuse rollback.'
}

$installedHash = Get-LowerHash $target
if ($installedHash -ne $manifest.installed_sha256) {
    throw 'Installed dxgi.dll hash changed. Refuse delete.'
}

$versionBefore = if (Test-Path -LiteralPath $version -PathType Leaf) { Get-LowerHash $version } else { $null }
$restoredPrevious = $false
$tempRestore = Assert-ChildPath $game (Join-Path $game "dxgi.dll.completionist-rollback-$PID.tmp")
$previous = $null
$restoreSha = ''
$restoreDllRelative = ''
$restoreManifestRelative = ''

if ($null -ne $manifest.backup_relative -and
    -not [string]::IsNullOrWhiteSpace([string]$manifest.backup_relative)) {
    $restoreDllRelative = [string]$manifest.backup_relative
    $restoreManifestRelative = [string]$manifest.backup_manifest_relative
    $backup = Assert-ChildPath $game (Join-Path $game $restoreDllRelative)
    $backupManifest = Assert-ChildPath $game (Join-Path $game $restoreManifestRelative)
    foreach ($path in @($backup, $backupManifest)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Need rollback backup: $path" }
    }
    $previous = Get-Content -Raw -LiteralPath $backupManifest | ConvertFrom-Json
    if ($previous.schema -ne $Schema -or
        $previous.owner -ne $Owner -or
        $previous.target_relative -ne $TargetRelative -or
        $previous.proxy_contract -ne $ProxyContract -or
        (Get-LowerHash $backup) -ne $previous.installed_sha256) {
        throw 'Rollback backup not known or hash changed.'
    }
    $restoreSha = ([string]$previous.installed_sha256).ToLowerInvariant()
}

$operationArgs = @{
    GameRoot = $game
    Operation = 'rollback'
    OperationSha256 = $installedHash
    RestoreExists = ($null -ne $previous)
    RestoreSha256 = $restoreSha
    RestoreDllRelative = $restoreDllRelative
    RestoreManifestRelative = $restoreManifestRelative
}
$operation = New-RavenBridgeOperation @operationArgs

try {
    if ($null -ne $previous) {
        Copy-Item -LiteralPath $backup -Destination $tempRestore -Force
        if ((Get-LowerHash $tempRestore) -ne $restoreSha) {
            throw 'Rollback staged DLL hash changed.'
        }
        Remove-Item -LiteralPath $target -Force
        Move-Item -LiteralPath $tempRestore -Destination $target
        Set-RavenBridgeOperationPhase -OperationPath $operation.Path -Journal $operation.Journal -Phase 'target-restored'

        $manifestCopyArgs = @{
            Source = $backupManifest
            Destination = $manifestPath
            ExpectedSha = (Get-RavenBridgeHash $backupManifest)
        }
        Copy-RavenBridgeFileAtomic @manifestCopyArgs
        Set-RavenBridgeOperationPhase -OperationPath $operation.Path -Journal $operation.Journal -Phase 'pair-restored'
        if ((Get-LowerHash $target) -ne $restoreSha) {
            throw 'Rollback restored DLL SHA differs.'
        }
        $restoredManifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
        [void](Assert-RavenBridgeOwnedManifest -Manifest $restoredManifest -ExpectedSha $restoreSha)
        $restoredPrevious = $true
    } else {
        Remove-Item -LiteralPath $target -Force
        Set-RavenBridgeOperationPhase -OperationPath $operation.Path -Journal $operation.Journal -Phase 'target-removed'
        Remove-Item -LiteralPath $manifestPath -Force
        Set-RavenBridgeOperationPhase -OperationPath $operation.Path -Journal $operation.Journal -Phase 'pair-removed'
        if ((Test-Path -LiteralPath $target) -or (Test-Path -LiteralPath $manifestPath)) {
            throw 'Clean bridge rollback did not remove owned pair.'
        }
    }
    Remove-Item -LiteralPath $operation.Path -Force
}
finally {
    if (Test-Path -LiteralPath $tempRestore -PathType Leaf) {
        Remove-Item -LiteralPath $tempRestore -Force
    }
}

$versionAfter = if (Test-Path -LiteralPath $version -PathType Leaf) { Get-LowerHash $version } else { $null }
if ($versionAfter -ne $versionBefore) { throw 'version.dll changed during rollback.' }

$nativeDir = Assert-ChildPath $game (Join-Path $game 'mods\completionist-map\native')
$receipt = Assert-ChildPath $game (Join-Path $nativeDir ("rollback-" + (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmssfff') + '.json'))
[ordered]@{
    schema = $Schema
    owner = $Owner
    rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
    removed_sha256 = $installedHash
    target_relative = $TargetRelative
    proxy_contract = $ProxyContract
    restored_previous = $restoredPrevious
    version_dll_untouched = $true
    save_writes = $false
    progression_writes = $false
} | ConvertTo-Json | Set-Content -LiteralPath $receipt -Encoding UTF8

Write-Host "RAVEN_NATIVE_BRIDGE_ROLLED_BACK target=dxgi.dll removed_sha256=$installedHash restored_previous=$($restoredPrevious.ToString().ToLowerInvariant()) version_untouched=true"
