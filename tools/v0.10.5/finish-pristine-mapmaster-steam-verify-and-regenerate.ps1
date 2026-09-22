[CmdletBinding()]
param(
    [string]$ExpectedBranch = 'codex/collectible-legendary-chests'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $RepoRoot
$branch = (& git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) { throw "Wrong branch '$branch'; expected '$ExpectedBranch'." }
$dirty = @(& git status --porcelain)
if ($dirty.Count -gt 0) {
    Write-Host 'Working tree is not clean:' -ForegroundColor Yellow
    $dirty | ForEach-Object { Write-Host "  $_" }
    throw 'Working tree must be clean before finalising pristine-mapmaster recovery.'
}
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
    throw 'Close God of War before finalising pristine mapmaster recovery.'
}

$RecoveryRoot = Join-Path $RepoRoot 'build\legendary-pristine-mapmaster-recovery'
$ActivePath = Join-Path $RecoveryRoot 'active.json'
if (-not (Test-Path -LiteralPath $ActivePath -PathType Leaf)) {
    throw "No active Steam-verify recovery session found: $ActivePath"
}
$active = Get-Content -LiteralPath $ActivePath -Raw | ConvertFrom-Json
$ManifestPath = [string]$active.manifest
if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { throw "Missing recovery manifest: $ManifestPath" }
$manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json

$GameRoot = [string]$manifest.game_root
$DcbDir = [string]$manifest.dcb_dir
$BackupDcbDir = [string]$manifest.backup_dcb_dir
$Mapmaster = Join-Path $DcbDir 'mapmaster.dcb'
$ExpectedSha = ([string]$manifest.expected_pristine_mapmaster.sha256).ToLowerInvariant()
$ExpectedBytes = [long]$manifest.expected_pristine_mapmaster.bytes

if (-not (Test-Path -LiteralPath $Mapmaster -PathType Leaf)) { throw "Steam validation has not produced mapmaster.dcb: $Mapmaster" }
$currentMap = Get-Item -LiteralPath $Mapmaster
$currentMapSha = (Get-FileHash -LiteralPath $Mapmaster -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "POST_STEAM_MAPMASTER bytes=$($currentMap.Length) sha=$currentMapSha"
if ($currentMap.Length -ne $ExpectedBytes -or $currentMapSha -ne $ExpectedSha) {
    throw "Steam validation has not produced the required pristine native mapmaster.dcb. Expected sha=$ExpectedSha bytes=$ExpectedBytes, got sha=$currentMapSha bytes=$($currentMap.Length). Raven backup remains untouched at $BackupDcbDir."
}

$CacheDir = Join-Path $RepoRoot 'build\native-source-cache'
$CachePath = Join-Path $CacheDir 'mapmaster.dcb'
New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null
Copy-Item -LiteralPath $Mapmaster -Destination $CachePath -Force
$cache = Get-Item -LiteralPath $CachePath
$cacheSha = (Get-FileHash -LiteralPath $CachePath -Algorithm SHA256).Hash.ToLowerInvariant()
if ($cache.Length -ne $ExpectedBytes -or $cacheSha -ne $ExpectedSha) {
    throw 'Pristine mapmaster cache copy failed validation.'
}
Write-Host "PRISTINE_MAPMASTER_CAPTURED cache=$CachePath" -ForegroundColor Green

$expectedPaths = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
foreach ($row in @($manifest.files)) {
    $relative = [string]$row.relative_path
    $null = $expectedPaths.Add($relative)
    $source = Join-Path $BackupDcbDir $relative
    $target = Join-Path $DcbDir $relative
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Preserved Raven DCB file is missing: $source" }
    $sourceItem = Get-Item -LiteralPath $source
    $sourceSha = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($sourceItem.Length -ne [long]$row.bytes -or $sourceSha -ne ([string]$row.sha256).ToLowerInvariant()) {
        throw "Preserved Raven DCB backup failed validation before restore: $relative"
    }
    $parent = Split-Path -Parent $target
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Copy-Item -LiteralPath $source -Destination $target -Force
}

foreach ($file in @(Get-ChildItem -LiteralPath $DcbDir -File -Recurse)) {
    $relative = [IO.Path]::GetRelativePath($DcbDir, $file.FullName)
    if (-not $expectedPaths.Contains($relative)) {
        Remove-Item -LiteralPath $file.FullName -Force
    }
}

$restoredFiles = @(Get-ChildItem -LiteralPath $DcbDir -File -Recurse)
if ($restoredFiles.Count -ne @($manifest.files).Count) {
    throw "Restored DCB directory file-count mismatch. Expected $(@($manifest.files).Count), got $($restoredFiles.Count). Backup remains at $BackupDcbDir."
}
foreach ($row in @($manifest.files)) {
    $relative = [string]$row.relative_path
    $target = Join-Path $DcbDir $relative
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Restored DCB missing: $relative" }
    $item = Get-Item -LiteralPath $target
    $sha = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($item.Length -ne [long]$row.bytes -or $sha -ne ([string]$row.sha256).ToLowerInvariant()) {
        throw "Restored Raven DCB validation mismatch: $relative"
    }
}

$completion = [ordered]@{
    result = 'PRISTINE_MAPMASTER_CAPTURED_RAVEN_DCBS_RESTORED'
    completed_utc = (Get-Date).ToUniversalTime().ToString('o')
    pristine_mapmaster_cache = [IO.Path]::GetFullPath($CachePath)
    pristine_mapmaster_sha256 = $ExpectedSha
    pristine_mapmaster_bytes = $ExpectedBytes
    restored_dcb_files = @($manifest.files).Count
    preserved_backup = [IO.Path]::GetFullPath($BackupDcbDir)
}
$completionPath = Join-Path ([string]$active.session_dir) 'completion.json'
$completion | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $completionPath -Encoding UTF8
Remove-Item -LiteralPath $ActivePath -Force

Write-Host 'RAVEN_DCB_DIRECTORY_RESTORED_BYTE_FOR_BYTE' -ForegroundColor Green
Write-Host "  files=$(@($manifest.files).Count)"
Write-Host "  preserved_backup=$BackupDcbDir"
Write-Host ''

$Regenerator = Join-Path $RepoRoot 'tools\v0.10.5\regenerate-corrected-legendary-catalogue-and-push.ps1'
if (-not (Test-Path -LiteralPath $Regenerator -PathType Leaf)) { throw "Missing regenerator: $Regenerator" }
& pwsh -NoProfile -ExecutionPolicy Bypass -File $Regenerator -GameRoot $GameRoot -ExpectedBranch $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw "Legendary catalogue regeneration failed with exit code $LASTEXITCODE after Raven DCB restoration." }
