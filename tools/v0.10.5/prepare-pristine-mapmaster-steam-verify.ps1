[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
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
    throw 'Working tree must be clean before Steam-verify preservation.'
}
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
    throw 'Close God of War before preparing pristine mapmaster recovery.'
}

$DcbDir = Join-Path $GameRoot 'exec\dc\pc_le'
$Mapmaster = Join-Path $DcbDir 'mapmaster.dcb'
if (-not (Test-Path -LiteralPath $DcbDir -PathType Container)) { throw "Missing DCB directory: $DcbDir" }
if (-not (Test-Path -LiteralPath $Mapmaster -PathType Leaf)) { throw "Missing installed mapmaster: $Mapmaster" }

$RecoveryRoot = Join-Path $RepoRoot 'build\legendary-pristine-mapmaster-recovery'
$ActivePath = Join-Path $RecoveryRoot 'active.json'
if (Test-Path -LiteralPath $ActivePath -PathType Leaf) {
    throw "An unfinished pristine-mapmaster recovery already exists: $ActivePath. Finish or inspect it before starting another."
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$SessionDir = Join-Path $RecoveryRoot $stamp
$BackupDcbDir = Join-Path $SessionDir 'pc_le-before-steam-verify'
$ManifestPath = Join-Path $SessionDir 'preserve-manifest.json'
New-Item -ItemType Directory -Force -Path $BackupDcbDir | Out-Null

$sourceFiles = @(Get-ChildItem -LiteralPath $DcbDir -File -Recurse | Sort-Object FullName)
if ($sourceFiles.Count -lt 1) { throw "No files found under $DcbDir" }

foreach ($file in $sourceFiles) {
    $relative = [IO.Path]::GetRelativePath($DcbDir, $file.FullName)
    $destination = Join-Path $BackupDcbDir $relative
    $parent = Split-Path -Parent $destination
    if (-not (Test-Path -LiteralPath $parent -PathType Container)) {
        New-Item -ItemType Directory -Force -Path $parent | Out-Null
    }
    Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
}

$manifestRows = @()
foreach ($file in $sourceFiles) {
    $relative = [IO.Path]::GetRelativePath($DcbDir, $file.FullName)
    $backup = Join-Path $BackupDcbDir $relative
    if (-not (Test-Path -LiteralPath $backup -PathType Leaf)) { throw "Backup missing after copy: $relative" }
    $sourceSha = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    $backupSha = (Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash.ToLowerInvariant()
    $backupLength = (Get-Item -LiteralPath $backup).Length
    if ($sourceSha -ne $backupSha -or $file.Length -ne $backupLength) {
        throw "Backup validation mismatch for $relative"
    }
    $manifestRows += [ordered]@{
        relative_path = $relative
        bytes = [long]$file.Length
        sha256 = $sourceSha
    }
}

$currentMap = Get-Item -LiteralPath $Mapmaster
$currentMapSha = (Get-FileHash -LiteralPath $Mapmaster -Algorithm SHA256).Hash.ToLowerInvariant()
$manifest = [ordered]@{
    recovery = 'legendary-pristine-mapmaster-via-steam-verify'
    created_utc = (Get-Date).ToUniversalTime().ToString('o')
    branch = $ExpectedBranch
    game_root = [IO.Path]::GetFullPath($GameRoot)
    dcb_dir = [IO.Path]::GetFullPath($DcbDir)
    backup_dcb_dir = [IO.Path]::GetFullPath($BackupDcbDir)
    installed_mapmaster_before = [ordered]@{
        bytes = [long]$currentMap.Length
        sha256 = $currentMapSha
    }
    expected_pristine_mapmaster = [ordered]@{
        bytes = 75872
        sha256 = '1e1d5086815bc8553490bff915fea210a8be4f80ce6c88b418b62d7050690a31'
    }
    files = $manifestRows
}
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ManifestPath -Encoding UTF8

New-Item -ItemType Directory -Force -Path $RecoveryRoot | Out-Null
([ordered]@{
    session_dir = [IO.Path]::GetFullPath($SessionDir)
    manifest = [IO.Path]::GetFullPath($ManifestPath)
    created_utc = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 4) | Set-Content -LiteralPath $ActivePath -Encoding UTF8

Write-Host 'RAVEN_DCB_DIRECTORY_PRESERVED' -ForegroundColor Green
Write-Host "  files=$($manifestRows.Count)"
Write-Host "  backup=$BackupDcbDir"
Write-Host "  current_mapmaster_bytes=$($currentMap.Length)"
Write-Host "  current_mapmaster_sha256=$currentMapSha"
Write-Host ''
Write-Host 'Starting Steam file validation for God of War (AppID 1593500)...' -ForegroundColor Cyan
try {
    Start-Process 'steam://validate/1593500'
    Write-Host 'STEAM_VALIDATION_REQUESTED' -ForegroundColor Green
} catch {
    Write-Host 'Could not open the Steam validation URI automatically.' -ForegroundColor Yellow
    Write-Host 'Open Steam > God of War > Properties > Installed Files > Verify integrity of game files.' -ForegroundColor Yellow
}
Write-Host ''
Write-Host 'Do not launch God of War after validation.' -ForegroundColor Yellow
Write-Host 'When Steam reports validation complete, run tools\v0.10.5\finish-pristine-mapmaster-steam-verify-and-regenerate.ps1.' -ForegroundColor Yellow
