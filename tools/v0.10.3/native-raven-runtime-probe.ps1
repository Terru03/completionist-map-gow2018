param(
    [ValidateSet('Install', 'Remove')][string]$Mode,
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'research/v0.10.3-native-compass') {
    throw "Expected research/v0.10.3-native-compass, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before installing or removing the native Raven runtime probe.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$dcbDir = Join-Path $game 'exec\dc\pc_le'
$stateDir = Join-Path $repo 'build\v0.10.3-native-runtime'
$runtimeDir = Join-Path $stateDir 'game-root\exec\dc\pc_le'
$backupDir = Join-Path $stateDir 'stock-backup'
$saveBackupDir = Join-Path $stateDir 'save-backup'
$prepReport = Join-Path $stateDir 'prepared.json'
$manifestPath = Join-Path $stateDir 'active.json'
$lookupManifest = Join-Path $repo 'build\v0.10.3-lookup\active.json'
$lookupScript = Join-Path $PSScriptRoot 'lookup-probe.ps1'
$prepareScript = Join-Path $PSScriptRoot 'prepare-native-raven-runtime.py'
$utf8 = New-Object Text.UTF8Encoding($false)

$expectedExe = 'CAEBCB027980D7EAC9203D190F9EE649EEBC549F8DEFCE138E2114DC91F40452'
$stockHashes = [ordered]@{
    'mapmaster.dcb'    = 'AEC578E773898A1E60D5CCEDD0DF08E35B12AB54E4D26F4CD90740948430C2A0'
    'mapcoords.dcb'    = '5D0B7591032D7B56581A0D77946C3FAD4F0CBC1B9D245F3578407177C40BBE7D'
    'compassgraph.dcb' = 'C2FA6BAB0C7C1DBE413A41F477A5E01AB396731FC6F6D611047A8BD346A56C5E'
}

function Hash-File([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Get-SaveSnapshot([string]$Root) {
    $rows = @()
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) { return @() }
    $resolved = (Resolve-Path -LiteralPath $Root).Path.TrimEnd('\') + '\'
    foreach ($file in @(Get-ChildItem -LiteralPath $Root -Recurse -Force -File | Sort-Object FullName)) {
        $relative = $file.FullName.Substring($resolved.Length)
        $rows += [pscustomobject]@{
            path = $relative
            bytes = [int64]$file.Length
            sha256 = Hash-File $file.FullName
        }
    }
    return @($rows)
}

function Snapshot-ToMap($Rows) {
    $map = @{}
    foreach ($row in @($Rows)) {
        $map[[string]$row.path] = ([string]$row.sha256).ToUpperInvariant()
    }
    return $map
}

function Compare-SaveSnapshot($BeforeRows, $AfterRows) {
    $before = Snapshot-ToMap $BeforeRows
    $after = Snapshot-ToMap $AfterRows
    $all = @($before.Keys + $after.Keys | Sort-Object -Unique)
    $changed = @()
    foreach ($path in $all) {
        $b = if ($before.ContainsKey($path)) { $before[$path] } else { $null }
        $a = if ($after.ContainsKey($path)) { $after[$path] } else { $null }
        if ($b -ne $a) {
            $changed += [pscustomobject]@{ path = $path; before = $b; after = $a }
        }
    }
    return @($changed)
}

function Restore-Dcbs($Manifest) {
    foreach ($name in $stockHashes.Keys) {
        $target = Join-Path $dcbDir $name
        $backup = Join-Path $backupDir $name
        if (-not (Test-Path -LiteralPath $backup -PathType Leaf)) {
            throw "Missing DCB backup: $backup"
        }
        $stock = ([string]$Manifest.stock_hashes.$name).ToUpperInvariant()
        $patched = ([string]$Manifest.patched_hashes.$name).ToUpperInvariant()
        $current = Hash-File $target
        if ($current -ne $patched -and $current -ne $stock) {
            throw "$name changed after probe install. Refusing automatic overwrite. Backup preserved at $backup"
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
    throw 'GoW.exe differs from the researched build. Refusing native DCB runtime probe.'
}

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw 'No active native Raven runtime manifest.'
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

    if (Test-Path -LiteralPath $lookupManifest -PathType Leaf) {
        & $lookupScript -Mode Remove -GameRoot $game
    }

    Restore-Dcbs $manifest

    $saveRoot = [string]$manifest.save_root
    $afterSave = Get-SaveSnapshot $saveRoot
    $changes = Compare-SaveSnapshot @($manifest.save_snapshot_before) $afterSave
    if ($changes.Count -gt 0) {
        Write-Warning "Save data changed during the runtime test. Backup is preserved at: $saveBackupDir"
        foreach ($change in $changes) {
            Write-Warning ("SAVE_CHANGED {0}" -f $change.path)
        }
        Write-Warning 'No save file was restored automatically.'
    } else {
        Write-Host 'Save snapshot unchanged during test.'
    }

    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Native Raven runtime probe removed. All three stock DCBs restored byte-for-byte.'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Native Raven runtime probe is already active. Remove it first.'
}
if (Test-Path -LiteralPath $lookupManifest -PathType Leaf) {
    throw 'A lookup probe is already active. Remove it before installing the native DCB runtime probe.'
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

Write-Host 'Preparing neutral Raven runtime DCB copies...'
& $python.Source $prepareScript --game-root $game --repo-root $repo --output $prepReport
if ($LASTEXITCODE -ne 0) { throw 'Native Raven runtime DCB preparation failed.' }
$prep = Get-Content -LiteralPath $prepReport -Raw | ConvertFrom-Json
if ($prep.result -ne 'RUNTIME_DCB_COPIES_PREPARED_NOT_INSTALLED' -or
    [int]$prep.runtime_init_state -ne 0 -or
    $prep.game_files_written -ne $false -or
    $prep.compass_show_called -ne $false) {
    throw 'Prepared runtime DCB report failed safety checks.'
}

$patchedHashes = [ordered]@{}
foreach ($name in $stockHashes.Keys) {
    $source = Join-Path $runtimeDir $name
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Prepared DCB missing: $source" }
    $expectedPatched = ([string]$prep.generated_files.$name.sha256).ToUpperInvariant()
    if ((Hash-File $source) -ne $expectedPatched) { throw "Prepared $name hash mismatch." }
    $patchedHashes[$name] = $expectedPatched
}

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
foreach ($name in $stockHashes.Keys) {
    $target = Join-Path $dcbDir $name
    $backup = Join-Path $backupDir $name
    Copy-Item -LiteralPath $target -Destination $backup -Force
    if ((Hash-File $backup) -ne $stockHashes[$name]) { throw "Backup hash mismatch for $name" }
}

$saveRoot = Join-Path $env:USERPROFILE 'Saved Games\God of War'
$saveSnapshot = Get-SaveSnapshot $saveRoot
if (Test-Path -LiteralPath $saveBackupDir) { Remove-Item -LiteralPath $saveBackupDir -Recurse -Force }
if (Test-Path -LiteralPath $saveRoot -PathType Container) {
    New-Item -ItemType Directory -Force -Path $saveBackupDir | Out-Null
    Copy-Item -Path (Join-Path $saveRoot '*') -Destination $saveBackupDir -Recurse -Force
}

$manifest = [ordered]@{
    candidate = 'Completionist_V103_Veithurgard_Raven_01'
    candidate_hash = 'E15E6BC82AE2773E'
    game_root = $game
    stock_hashes = $stockHashes
    patched_hashes = $patchedHashes
    save_root = $saveRoot
    save_snapshot_before = @($saveSnapshot)
    save_backup = $saveBackupDir
    compass_show_called = $false
    installed_utc = [DateTime]::UtcNow.ToString('o')
}
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 6), $utf8)

try {
    foreach ($name in $stockHashes.Keys) {
        Copy-Item -LiteralPath (Join-Path $runtimeDir $name) -Destination (Join-Path $dcbDir $name) -Force
        if ((Hash-File (Join-Path $dcbDir $name)) -ne $patchedHashes[$name]) {
            throw "Installed hash mismatch for $name"
        }
    }

    & $lookupScript -Mode Install -GameRoot $game
} catch {
    try {
        if (Test-Path -LiteralPath $lookupManifest -PathType Leaf) {
            & $lookupScript -Mode Remove -GameRoot $game
        }
        $recoveryManifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        Restore-Dcbs $recoveryManifest
    } catch {
        Write-Warning "Automatic recovery also failed: $($_.Exception.Message)"
    }
    throw
}

Write-Host ''
Write-Host 'Native Raven DCB runtime lookup probe installed.'
Write-Host 'The Raven token uses InitState=0 (undiscovered). No marker state was changed.'
Write-Host 'Compass.ShowMarker is NOT called by this test.'
Write-Host "Save backup: $saveBackupDir"
Write-Host ''
Write-Host 'Next: launch God of War, load the Veithurgard save, open the Midgard map ONCE, then close the game.'
Write-Host 'Do not press Add to Compass.'
Write-Host ("Rollback: powershell -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
