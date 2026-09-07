param(
    [ValidateSet('Install', 'Remove')][string]$Mode,
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.3-native-raven') {
    throw "Expected feat/v0.10.3-native-raven, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before installing or removing the native Raven DCBs.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$dcbDir = Join-Path $game 'exec\dc\pc_le'
$stateDir = Join-Path $repo 'build\v0.10.3-native-raven-dcb'
$runtimeDir = Join-Path $repo 'build\v0.10.3-native-runtime\game-root\exec\dc\pc_le'
$backupDir = Join-Path $stateDir 'stock-backup'
$manifestPath = Join-Path $stateDir 'active.json'
$prepReport = Join-Path $stateDir 'prepared.json'
$prepareScript = Join-Path $PSScriptRoot 'prepare-native-raven-runtime.py'
$utf8 = New-Object Text.UTF8Encoding($false)

$expectedExe = 'CAEBCB027980D7EAC9203D190F9EE649EEBC549F8DEFCE138E2114DC91F40452'
$stockHashes = [ordered]@{
    'mapmaster.dcb'    = 'AEC578E773898A1E60D5CCEDD0DF08E35B12AB54E4D26F4CD90740948430C2A0'
    'mapcoords.dcb'    = '5D0B7591032D7B56581A0D77946C3FAD4F0CBC1B9D245F3578407177C40BBE7D'
    'compassgraph.dcb' = 'C2FA6BAB0C7C1DBE413A41F477A5E01AB396731FC6F6D611047A8BD346A56C5E'
}

function Hash-File([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Restore-Dcbs($Manifest) {
    foreach ($name in $stockHashes.Keys) {
        $target = Join-Path $dcbDir $name
        $backup = Join-Path $backupDir $name
        if (-not (Test-Path -LiteralPath $backup -PathType Leaf)) {
            throw "Missing stock backup: $backup"
        }
        $stock = ([string]$Manifest.stock_hashes.$name).ToUpperInvariant()
        $patched = ([string]$Manifest.patched_hashes.$name).ToUpperInvariant()
        $current = Hash-File $target
        if ($current -ne $patched -and $current -ne $stock) {
            throw "$name changed after install. Refusing automatic overwrite; backup preserved at $backup"
        }
        if ($current -ne $stock) {
            Copy-Item -LiteralPath $backup -Destination $target -Force
        }
        if ((Hash-File $target) -ne $stock) {
            throw "$name rollback hash mismatch."
        }
    }
}

$exe = Join-Path $game 'GoW.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf) -or (Hash-File $exe) -ne $expectedExe) {
    throw 'GoW.exe differs from the researched build. Refusing native Raven DCB install.'
}

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Native Raven DCB candidate is already removed.'
        return
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    Restore-Dcbs $manifest
    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Native Raven DCB candidate removed. Stock DCBs restored byte-for-byte.'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Native Raven DCB candidate is already installed.'
}

foreach ($name in $stockHashes.Keys) {
    $target = Join-Path $dcbDir $name
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Missing stock DCB: $target" }
    if ((Hash-File $target) -ne $stockHashes[$name]) {
        throw "$name is not the researched stock file. Refusing install."
    }
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
Write-Host 'Preparing validated Raven native DCB copies...'
& $python.Source $prepareScript --game-root $game --repo-root $repo --output $prepReport
if ($LASTEXITCODE -ne 0) { throw 'Raven DCB preparation failed.' }
$prep = Get-Content -LiteralPath $prepReport -Raw | ConvertFrom-Json
if ($prep.result -ne 'RUNTIME_DCB_COPIES_PREPARED_NOT_INSTALLED' -or
    [int]$prep.runtime_init_state -ne 0 -or
    $prep.game_files_written -ne $false -or
    $prep.compass_show_called -ne $false) {
    throw 'Prepared DCB report failed safety checks.'
}

$patchedHashes = [ordered]@{}
foreach ($name in $stockHashes.Keys) {
    $source = Join-Path $runtimeDir $name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Prepared DCB missing: $source" }
    $expectedPatched = ([string]$prep.generated_files.$name.sha256).ToUpperInvariant()
    if ((Hash-File $source) -ne $expectedPatched) { throw "Prepared $name hash mismatch." }
    $patchedHashes[$name] = $expectedPatched
}

if (Test-Path -LiteralPath $backupDir) { Remove-Item -LiteralPath $backupDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
foreach ($name in $stockHashes.Keys) {
    $target = Join-Path $dcbDir $name
    $backup = Join-Path $backupDir $name
    Copy-Item -LiteralPath $target -Destination $backup -Force
    if ((Hash-File $backup) -ne $stockHashes[$name]) { throw "Backup hash mismatch for $name" }
}

$manifest = [ordered]@{
    candidate = 'Completionist_V103_Veithurgard_Raven_01'
    candidate_hash = 'E15E6BC82AE2773E'
    stock_hashes = $stockHashes
    patched_hashes = $patchedHashes
    installed_utc = [DateTime]::UtcNow.ToString('o')
}
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 5), $utf8)

try {
    foreach ($name in $stockHashes.Keys) {
        $target = Join-Path $dcbDir $name
        Copy-Item -LiteralPath (Join-Path $runtimeDir $name) -Destination $target -Force
        if ((Hash-File $target) -ne $patchedHashes[$name]) {
            throw "Installed hash mismatch for $name"
        }
    }
} catch {
    try {
        $recovery = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        Restore-Dcbs $recovery
    } catch {
        Write-Warning "Automatic DCB recovery also failed: $($_.Exception.Message)"
    }
    throw
}

Write-Host 'Native Raven DCB candidate installed.'
Write-Host 'Marker: Completionist_V103_Veithurgard_Raven_01 / E15E6BC82AE2773E'
Write-Host 'InitState remains 0. No marker progression state was changed.'
Write-Host 'Compass.ShowMarker has not been called by this installer.'
