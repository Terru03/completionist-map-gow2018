[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$ExpectedBranch = 'codex/collectible-legendary-chests'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$NativeMapmasterSha = '1e1d5086815bc8553490bff915fea210a8be4f80ce6c88b418b62d7050690a31'
$NativeMapmasterBytes = 75872

$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $RepoRoot

$branch = (& git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) { throw "Wrong branch '$branch'; expected '$ExpectedBranch'." }
$dirty = @(& git status --porcelain)
if ($dirty.Count -gt 0) {
    Write-Host 'Working tree is not clean:' -ForegroundColor Yellow
    $dirty | ForEach-Object { Write-Host "  $_" }
    throw 'Working tree must be clean before pristine mapmaster recovery.'
}
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
    throw 'Close God of War before pristine mapmaster recovery and static catalogue regeneration.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }
$Regenerator = Join-Path $RepoRoot 'tools\v0.10.5\regenerate-corrected-legendary-catalogue-and-push.ps1'
if (-not (Test-Path -LiteralPath $Regenerator -PathType Leaf)) { throw "Missing regenerator: $Regenerator" }

function Test-PristineMapmaster([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -ne $NativeMapmasterBytes) { return $false }
    $sha = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    return $sha -eq $NativeMapmasterSha
}

$cacheDir = Join-Path $RepoRoot 'build\native-source-cache'
$cachePath = Join-Path $cacheDir 'mapmaster.dcb'
New-Item -ItemType Directory -Force -Path $cacheDir | Out-Null

# First search every plausible preserved filesystem copy. This intentionally includes
# archive/ and the whole game root because older Raven transaction backups were not
# guaranteed to live under build/ or mods/.
$roots = @(
    (Join-Path $RepoRoot 'build'),
    (Join-Path $RepoRoot 'archive'),
    $GameRoot
)
$seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$filesystemCandidates = New-Object System.Collections.Generic.List[object]
foreach ($root in $roots) {
    if (-not (Test-Path -LiteralPath $root -PathType Container)) { continue }
    foreach ($item in @(Get-ChildItem -LiteralPath $root -Filter 'mapmaster.dcb' -Recurse -File -ErrorAction SilentlyContinue)) {
        if ($seen.Add($item.FullName)) { $filesystemCandidates.Add($item) | Out-Null }
    }
}
Write-Host "FILESYSTEM_MAPMASTER_CANDIDATES $($filesystemCandidates.Count)"
foreach ($item in $filesystemCandidates) {
    $sha = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "  bytes=$($item.Length) sha=$sha path=$($item.FullName)"
    if ($item.Length -eq $NativeMapmasterBytes -and $sha -eq $NativeMapmasterSha) {
        Copy-Item -LiteralPath $item.FullName -Destination $cachePath -Force
        if (-not (Test-PristineMapmaster $cachePath)) { throw 'Filesystem recovery copy failed post-copy validation.' }
        Write-Host "PRISTINE_MAPMASTER_RECOVERED filesystem=$($item.FullName) cache=$cachePath" -ForegroundColor Green
        & pwsh -NoProfile -ExecutionPolicy Bypass -File $Regenerator -GameRoot $GameRoot -ExpectedBranch $ExpectedBranch
        exit $LASTEXITCODE
    }
}

# If no filesystem copy survives, search the local Git object database. We only
# consider historical blobs whose recorded path ends in mapmaster.dcb, require the
# exact byte count before materialising, and verify SHA-256 afterwards.
$objects = @(& git rev-list --objects --all)
if ($LASTEXITCODE -ne 0) { throw 'git rev-list --objects --all failed.' }
$historical = @{}
foreach ($line in $objects) {
    if ($line -notmatch '^([0-9a-fA-F]{40})\s+(.+)$') { continue }
    $oid = $Matches[1].ToLowerInvariant()
    $path = $Matches[2]
    if (-not $path.EndsWith('mapmaster.dcb', [StringComparison]::OrdinalIgnoreCase)) { continue }
    if (-not $historical.ContainsKey($oid)) { $historical[$oid] = $path }
}
Write-Host "GIT_HISTORY_MAPMASTER_BLOBS $($historical.Count)"
foreach ($entry in $historical.GetEnumerator()) {
    $oid = [string]$entry.Key
    $path = [string]$entry.Value
    $type = (& git cat-file -t $oid 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or $type -ne 'blob') { continue }
    $sizeText = (& git cat-file -s $oid 2>$null).Trim()
    if ($LASTEXITCODE -ne 0) { continue }
    $size = 0L
    if (-not [long]::TryParse($sizeText, [ref]$size)) { continue }
    Write-Host "  git_blob=$oid bytes=$size path=$path"
    if ($size -ne $NativeMapmasterBytes) { continue }

    & $python.Source -c "import pathlib,subprocess,sys; pathlib.Path(sys.argv[2]).write_bytes(subprocess.check_output(['git','cat-file','blob',sys.argv[1]]))" $oid $cachePath
    if ($LASTEXITCODE -ne 0) { throw "Failed to materialise historical Git blob $oid" }
    $sha = (Get-FileHash -LiteralPath $cachePath -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Host "    materialised_sha=$sha"
    if ($sha -eq $NativeMapmasterSha) {
        Write-Host "PRISTINE_MAPMASTER_RECOVERED git_blob=$oid historical_path=$path cache=$cachePath" -ForegroundColor Green
        & pwsh -NoProfile -ExecutionPolicy Bypass -File $Regenerator -GameRoot $GameRoot -ExpectedBranch $ExpectedBranch
        exit $LASTEXITCODE
    }
    Remove-Item -LiteralPath $cachePath -Force -ErrorAction SilentlyContinue
}

throw "Could not recover pristine native mapmaster.dcb SHA=$NativeMapmasterSha bytes=$NativeMapmasterBytes from filesystem backups, archive evidence, the game tree, or historical Git blobs. No validation was weakened and catalogue regeneration was not attempted."
