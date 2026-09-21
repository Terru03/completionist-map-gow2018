param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$BridgeDll,
    [string]$BuildManifest
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedExeHash = 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452'
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

$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
if ([string]::IsNullOrWhiteSpace($BridgeDll)) {
    $BridgeDll = Join-Path $repo 'build\raven-authority-bridge\Release\dxgi.dll'
}
if ([string]::IsNullOrWhiteSpace($BuildManifest)) {
    $BuildManifest = Join-Path $repo 'build\raven-authority-bridge\bridge-build-manifest.json'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$exe = Assert-ChildPath $game (Join-Path $game 'GoW.exe')
$version = Assert-ChildPath $game (Join-Path $game 'version.dll')
$target = Assert-ChildPath $game (Join-Path $game $TargetRelative)
$manifestPath = Assert-ChildPath $game (Join-Path $game $ManifestRelative)

foreach ($path in @($exe, $version, $BridgeDll, $BuildManifest)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Need file: $path" }
}

$exeHash = Get-LowerHash $exe
if ($exeHash -ne $ExpectedExeHash) { throw "GoW.exe hash not supported: $exeHash" }
$versionBefore = Get-LowerHash $version

$build = Get-Content -Raw -LiteralPath $BuildManifest | ConvertFrom-Json
if ($build.schema -ne $Schema -or
    $build.owner -ne $Owner -or
    $build.target_relative -ne $TargetRelative -or
    $build.proxy_contract -ne $ProxyContract -or
    $build.supported_exe_sha256 -ne $ExpectedExeHash) {
    throw 'Build manifest not known.'
}

$bridgeHash = Get-LowerHash $BridgeDll
if ($bridgeHash -ne $build.dll_sha256) { throw 'Built DLL hash does not match build manifest.' }

$targetExists = Test-Path -LiteralPath $target -PathType Leaf
$manifestExists = Test-Path -LiteralPath $manifestPath -PathType Leaf
if ($targetExists -ne $manifestExists) {
    throw 'Existing dxgi.dll or bridge manifest has no matching pair. Refuse overwrite.'
}

$oldManifest = $null
$backupRelative = $null
$backupManifestRelative = $null
if ($targetExists) {
    $oldManifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
    if ($oldManifest.schema -ne $Schema -or
        $oldManifest.owner -ne $Owner -or
        $oldManifest.target_relative -ne $TargetRelative -or
        $oldManifest.proxy_contract -ne $ProxyContract) {
        throw 'Existing dxgi.dll is not a known Completionist Map bridge. Refuse overwrite.'
    }
    $oldHash = Get-LowerHash $target
    if ($oldHash -ne $oldManifest.installed_sha256) {
        throw 'Existing bridge hash changed. Refuse overwrite.'
    }
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmssfff')
    $backupRelative = "mods\completionist-map\native\backups\dxgi-$stamp-$($oldHash.Substring(0,12)).dll"
    $backupManifestRelative = "mods\completionist-map\native\backups\manifest-$stamp-$($oldHash.Substring(0,12)).json"
}

$nativeDir = Assert-ChildPath $game (Split-Path -Parent $manifestPath)
New-Item -ItemType Directory -Force -Path $nativeDir | Out-Null
$tempTarget = Assert-ChildPath $game (Join-Path $game "dxgi.dll.completionist-$PID.tmp")
$installed = $false

try {
    Copy-Item -LiteralPath $BridgeDll -Destination $tempTarget -Force
    if ((Get-LowerHash $tempTarget) -ne $bridgeHash) { throw 'Temporary DLL copy hash changed.' }

    if ($targetExists) {
        $backup = Assert-ChildPath $game (Join-Path $game $backupRelative)
        $backupManifest = Assert-ChildPath $game (Join-Path $game $backupManifestRelative)
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backup) | Out-Null
        Copy-Item -LiteralPath $target -Destination $backup
        Copy-Item -LiteralPath $manifestPath -Destination $backupManifest
        if ((Get-LowerHash $backup) -ne $oldManifest.installed_sha256) {
            throw 'Bridge backup hash changed.'
        }
    }

    if ($targetExists) { Remove-Item -LiteralPath $target -Force }
    Move-Item -LiteralPath $tempTarget -Destination $target

    $installManifest = [ordered]@{
        schema = $Schema
        owner = $Owner
        installed_utc = (Get-Date).ToUniversalTime().ToString('o')
        target_relative = $TargetRelative
        proxy_contract = $ProxyContract
        installed_sha256 = $bridgeHash
        supported_exe_sha256 = $exeHash
        version_dll_sha256 = $versionBefore
        build_git_commit = $build.git_commit
        backup_relative = $backupRelative
        backup_manifest_relative = $backupManifestRelative
        save_writes = $false
        progression_writes = $false
    }

    $tempManifest = Assert-ChildPath $game ($manifestPath + ".tmp-$PID")
    $installManifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $tempManifest -Encoding UTF8
    Move-Item -LiteralPath $tempManifest -Destination $manifestPath -Force

    if ((Get-LowerHash $target) -ne $bridgeHash) { throw 'Installed bridge hash changed.' }
    if ((Get-LowerHash $version) -ne $versionBefore) { throw 'version.dll changed during install.' }
    $installed = $true
}
catch {
    if (Test-Path -LiteralPath $tempTarget) { Remove-Item -LiteralPath $tempTarget -Force }
    if (-not $installed) {
        if ($targetExists -and $null -ne $backupRelative) {
            $backup = Assert-ChildPath $game (Join-Path $game $backupRelative)
            $backupManifest = Assert-ChildPath $game (Join-Path $game $backupManifestRelative)
            if (Test-Path -LiteralPath $backup -PathType Leaf) {
                Copy-Item -LiteralPath $backup -Destination $target -Force
            }
            if (Test-Path -LiteralPath $backupManifest -PathType Leaf) {
                Copy-Item -LiteralPath $backupManifest -Destination $manifestPath -Force
            }
        } elseif (-not $targetExists) {
            if (Test-Path -LiteralPath $target -PathType Leaf) {
                Remove-Item -LiteralPath $target -Force
            }
            if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
                Remove-Item -LiteralPath $manifestPath -Force
            }
        }
    }
    throw
}

Write-Host "RAVEN_NATIVE_BRIDGE_INSTALLED target=dxgi.dll proxy_sha256=$bridgeHash contract=$ProxyContract version_untouched=true manifest=$manifestPath"
