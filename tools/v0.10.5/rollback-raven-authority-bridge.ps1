param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Owner = 'completionist-map-raven-authority-bridge'
$TargetRelative = 'dxgi.dll'
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
$game = [IO.Path]::GetFullPath($GameRoot)
$target = Assert-ChildPath $game (Join-Path $game $TargetRelative)
$version = Assert-ChildPath $game (Join-Path $game 'version.dll')
$manifestPath = Assert-ChildPath $game (Join-Path $game $ManifestRelative)
foreach ($path in @($target, $manifestPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Need installed bridge file: $path" }
}
$manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
if ($manifest.schema -ne 1 -or $manifest.owner -ne $Owner -or $manifest.target_relative -ne $TargetRelative) {
    throw 'Bridge manifest not known. Refuse rollback.'
}
$installedHash = Get-LowerHash $target
if ($installedHash -ne $manifest.installed_sha256) {
    throw 'Installed dxgi.dll hash changed. Refuse delete.'
}
$versionBefore = if (Test-Path -LiteralPath $version -PathType Leaf) { Get-LowerHash $version } else { $null }
$restoredPrevious = $false
if ($null -ne $manifest.backup_relative -and -not [string]::IsNullOrWhiteSpace([string]$manifest.backup_relative)) {
    $backup = Assert-ChildPath $game (Join-Path $game ([string]$manifest.backup_relative))
    $backupManifest = Assert-ChildPath $game (Join-Path $game ([string]$manifest.backup_manifest_relative))
    foreach ($path in @($backup, $backupManifest)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Need rollback backup: $path" }
    }
    $previous = Get-Content -Raw -LiteralPath $backupManifest | ConvertFrom-Json
    if ($previous.schema -ne 1 -or $previous.owner -ne $Owner -or
        (Get-LowerHash $backup) -ne $previous.installed_sha256) {
        throw 'Rollback backup not known or hash changed.'
    }
    Remove-Item -LiteralPath $target -Force
    Copy-Item -LiteralPath $backup -Destination $target
    Copy-Item -LiteralPath $backupManifest -Destination $manifestPath -Force
    $restoredPrevious = $true
} else {
    Remove-Item -LiteralPath $target -Force
    Remove-Item -LiteralPath $manifestPath -Force
}
$versionAfter = if (Test-Path -LiteralPath $version -PathType Leaf) { Get-LowerHash $version } else { $null }
if ($versionAfter -ne $versionBefore) { throw 'version.dll changed during rollback.' }

$nativeDir = Assert-ChildPath $game (Join-Path $game 'mods\completionist-map\native')
$receipt = Assert-ChildPath $game (Join-Path $nativeDir ("rollback-" + (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmssfff') + '.json'))
[ordered]@{
    schema = 1
    owner = $Owner
    rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
    removed_sha256 = $installedHash
    restored_previous = $restoredPrevious
    version_dll_untouched = $true
    save_writes = $false
    progression_writes = $false
} | ConvertTo-Json | Set-Content -LiteralPath $receipt -Encoding UTF8

Write-Host "RAVEN_NATIVE_BRIDGE_ROLLED_BACK removed_sha256=$installedHash restored_previous=$($restoredPrevious.ToString().ToLowerInvariant()) version_untouched=true"
