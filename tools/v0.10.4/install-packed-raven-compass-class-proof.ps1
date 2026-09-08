param(
    [ValidateSet('Install', 'Remove')][string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before installing or removing the packed Raven compass-class proof.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$dcbDir = Join-Path $game 'exec\dc\pc_le'
$mapTarget = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$stateDir = Join-Path $repo 'build\v0.10.4-packed-raven-runtime'
$backupDir = Join-Path $stateDir 'baseline-backup'
$manifestPath = Join-Path $stateDir 'active.json'
$mapBackup = Join-Path $stateDir 'mapmenu-before.lua'
$classReport = Join-Path $stateDir 'packed-compass-class-prepared.json'
$runtime3Dir = Join-Path $repo 'build\v0.10.3-native-runtime\game-root\exec\dc\pc_le'
$classOutput = Join-Path $repo 'build\v0.10.4-packed-raven-compass-class\game-root\exec\dc\pc_le\wad_r_perm.dcb'
$classBuilder = Join-Path $PSScriptRoot 'build-packed-raven-compass-class.py'
$bridge = Join-Path $PSScriptRoot 'dedicated-raven-compass-class.lua'
$utf8 = New-Object Text.UTF8Encoding($false)

$expectedExe = 'CAEBCB027980D7EAC9203D190F9EE649EEBC549F8DEFCE138E2114DC91F40452'

# This proof must start from the currently proven v0.10.4 Raven-map baseline.
# mapmaster.dcb is intentionally NOT stock anymore: B930... is the working
# v0.10.4 mapmaster that already carries the authored Raven token/map wiring.
# Reverting it to the old stock/v0.10.3 mapmaster would destroy later v0.10.4 work.
$baselineHashes = [ordered]@{
    'mapmaster.dcb'    = 'B930C51316CA136D9C40EA7CDA6A63A051127B357E97F1D4E4EB96A16993D96F'
    'mapcoords.dcb'    = '5D0B7591032D7B56581A0D77946C3FAD4F0CBC1B9D245F3578407177C40BBE7D'
    'compassgraph.dcb' = 'C2FA6BAB0C7C1DBE413A41F477A5E01AB396731FC6F6D611047A8BD346A56C5E'
    'wad_r_perm.dcb'   = 'EABB9E548202E2F710520A0FAB905952CEFC10FFB2B6B5540E773D64EB1D8039'
}

# These are the already-proven native Raven coordinate/graph copies produced by
# the v0.10.3 runtime builder. They are compatible with the later v0.10.4
# mapmaster and were the exact files present during the proven Raven runtime.
$expectedPreparedHashes = [ordered]@{
    'mapcoords.dcb'    = '945774DBC965F45AD78B8408BB1D2B10A527C6390E4E7C1190E8F2D7538DF3CB'
    'compassgraph.dcb' = 'D0ED78BA4B91813C74DC6088A8521D332EA991E760B1C2600D6EEEFC5FE60E68'
}

function Hash-File([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Restore-Proof($Manifest) {
    $baseline = if ($null -ne $Manifest.baseline_hashes) { $Manifest.baseline_hashes } else { $Manifest.stock_hashes }
    foreach ($name in $baselineHashes.Keys) {
        $target = Join-Path $dcbDir $name
        $backup = Join-Path $backupDir $name
        if (-not (Test-Path -LiteralPath $backup -PathType Leaf)) {
            throw "Missing DCB baseline backup: $backup"
        }
        $before = ([string]$baseline.$name).ToUpperInvariant()
        $patched = ([string]$Manifest.patched_hashes.$name).ToUpperInvariant()
        $current = Hash-File $target
        if ($current -ne $before -and $current -ne $patched) {
            throw "$name changed after proof install. Refusing automatic overwrite. Backup preserved at $backup"
        }
        if ($current -ne $before) {
            Copy-Item -LiteralPath $backup -Destination $target -Force
        }
        if ((Hash-File $target) -ne $before) { throw "$name rollback hash mismatch." }
    }

    if (-not (Test-Path -LiteralPath $mapBackup -PathType Leaf)) { throw "Missing mapmenu backup: $mapBackup" }
    $mapBefore = ([string]$Manifest.map_before).ToUpperInvariant()
    $mapPatched = ([string]$Manifest.map_after).ToUpperInvariant()
    $mapCurrent = Hash-File $mapTarget
    if ($mapCurrent -ne $mapBefore -and $mapCurrent -ne $mapPatched) {
        throw 'mapmenu.lua changed after proof install. Refusing automatic overwrite.'
    }
    if ($mapCurrent -ne $mapBefore) {
        Copy-Item -LiteralPath $mapBackup -Destination $mapTarget -Force
    }
    if ((Hash-File $mapTarget) -ne $mapBefore) { throw 'mapmenu.lua rollback hash mismatch.' }
}

$exe = Join-Path $game 'GoW.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf) -or (Hash-File $exe) -ne $expectedExe) {
    throw 'GoW.exe differs from the researched build. Refusing packed Raven class proof.'
}

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Packed Raven compass-class proof is already removed.'
        return
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    Restore-Proof $manifest
    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Packed Raven compass-class proof removed.'
    Write-Host 'The proven pre-proof v0.10.4 DCB/mapmenu baseline was restored byte-for-byte.'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Packed Raven compass-class proof is already installed.'
}

$conflicting = @(
    (Join-Path $repo 'build\v0.10.4-dedicated-raven-runtime\active.json'),
    (Join-Path $repo 'build\v0.10.3-native-raven-candidate\active.json'),
    (Join-Path $repo 'build\v0.10.3-native-raven-dcb\active.json'),
    (Join-Path $repo 'build\v0.10.3-native-show\active.json'),
    (Join-Path $repo 'build\v0.10.3-native-runtime\active.json'),
    (Join-Path $repo 'build\v0.10.3-lookup\active.json')
)
foreach ($path in $conflicting) {
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        throw "A previous native proof/candidate is still active: $path"
    }
}
foreach ($path in @($mapTarget, $classBuilder, $bridge)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing required file: $path" }
}

Write-Host 'Validating the proven v0.10.4 Raven-map baseline...'
foreach ($name in $baselineHashes.Keys) {
    $target = Join-Path $dcbDir $name
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Missing baseline DCB: $target" }
    $actual = Hash-File $target
    if ($actual -ne $baselineHashes[$name]) {
        throw "$name differs from the proven pre-proof v0.10.4 baseline. Expected $($baselineHashes[$name]), got $actual"
    }
}

$mapSource = [IO.File]::ReadAllText($mapTarget)
if (-not $mapSource.Contains('[CompletionistMap v0.10.1] MAP_SCRIPT_LOADED')) {
    throw 'Expected tested Completionist map override was not found.'
}
if (-not $mapSource.Contains('function MapOn:ShowOnCompass(currState)')) {
    throw 'MapOn:ShowOnCompass missing from installed override.'
}
if (-not $mapSource.Contains('goMapIconCompletionistRaven')) {
    throw 'Expected proven v0.10.4 Raven map icon binding was not found.'
}
if ($mapSource.Contains('BEGIN COMPLETIONIST V0.10.4 DEDICATED RAVEN COMPASS CLASS')) {
    throw 'Dedicated Raven class bridge already appears in mapmenu.lua.'
}

# Do not rerun prepare-native-raven-runtime.py here: it requires the old stock
# mapmaster and would therefore reject or overwrite the proven v0.10.4 mapmaster.
# Reuse only the two native coordinate/graph copies whose hashes are known from
# the already-proven Raven runtime; mapmaster remains untouched.
$preparedSources = [ordered]@{
    'mapcoords.dcb'    = Join-Path $runtime3Dir 'mapcoords.dcb'
    'compassgraph.dcb' = Join-Path $runtime3Dir 'compassgraph.dcb'
}
Write-Host 'Validating previously proven Raven coordinate/graph runtime copies...'
foreach ($name in $preparedSources.Keys) {
    $source = $preparedSources[$name]
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Prepared Raven runtime file is missing: $source"
    }
    $actual = Hash-File $source
    if ($actual -ne $expectedPreparedHashes[$name]) {
        throw "Prepared $name hash mismatch. Expected $($expectedPreparedHashes[$name]), got $actual"
    }
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

Write-Host 'Building packed CompletionistRaven CompassIconClass candidate...'
New-Item -ItemType Directory -Force -Path (Split-Path $classOutput -Parent) | Out-Null
& $python.Source $classBuilder --game-root $game --output $classOutput --report $classReport
if ($LASTEXITCODE -ne 0) { throw 'Packed Raven CompassIconClass build failed.' }
$class = Get-Content -LiteralPath $classReport -Raw | ConvertFrom-Json
if ($class.result -ne 'OFFLINE_PACKED_COMPLETIONIST_RAVEN_COMPASS_CLASS_BUILT' -or
    $class.game_files_written -ne $false -or
    $class.installed -ne $false -or
    [string]$class.new_class.name -ne 'CompletionistRaven' -or
    [string]$class.new_class.uid -ne '5DC46967D3095F7E' -or
    [string]$class.new_class.root -ne '0x4E2C50' -or
    $class.new_class.record_bytes_equal_dockpoint -ne $true -or
    $class.validation.candidate_exact_0x20_stride -ne $true -or
    [string]$class.validation.COMPASS_GLOBALS_shifted_to -ne '0x4E2C70' -or
    $class.validation.all_stock_exports_preserved -ne $true -or
    $class.validation.all_stock_relocations_preserved_semantically -ne $true) {
    throw 'Packed Raven class build report failed validation.'
}

$patchedSources = [ordered]@{
    'mapcoords.dcb'    = $preparedSources['mapcoords.dcb']
    'compassgraph.dcb' = $preparedSources['compassgraph.dcb']
    'wad_r_perm.dcb'   = $classOutput
}
$patchedHashes = [ordered]@{
    'mapmaster.dcb'    = $baselineHashes['mapmaster.dcb']
    'mapcoords.dcb'    = $expectedPreparedHashes['mapcoords.dcb']
    'compassgraph.dcb' = $expectedPreparedHashes['compassgraph.dcb']
    'wad_r_perm.dcb'   = ([string]$class.candidate_sha256).ToUpperInvariant()
}
foreach ($name in $patchedSources.Keys) {
    $source = $patchedSources[$name]
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Prepared file missing: $source" }
    if ((Hash-File $source) -ne $patchedHashes[$name]) { throw "$name prepared hash mismatch." }
    if ($patchedHashes[$name] -eq $baselineHashes[$name]) { throw "$name proof copy unexpectedly equals baseline." }
}

if (Test-Path -LiteralPath $backupDir) { Remove-Item -LiteralPath $backupDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
foreach ($name in $baselineHashes.Keys) {
    $target = Join-Path $dcbDir $name
    $backup = Join-Path $backupDir $name
    Copy-Item -LiteralPath $target -Destination $backup -Force
    if ((Hash-File $backup) -ne $baselineHashes[$name]) { throw "Baseline backup hash mismatch for $name" }
}
$mapBefore = Hash-File $mapTarget
Copy-Item -LiteralPath $mapTarget -Destination $mapBackup -Force
if ((Hash-File $mapBackup) -ne $mapBefore) { throw 'mapmenu backup hash mismatch.' }

$bridgeText = [IO.File]::ReadAllText($bridge)
$patchedMap = $mapSource + "`r`n" + $bridgeText + "`r`n"
[IO.File]::WriteAllText($mapTarget, $patchedMap, $utf8)
$mapAfter = Hash-File $mapTarget
if ($mapAfter -eq $mapBefore) { throw 'mapmenu.lua was not patched.' }

$manifest = [ordered]@{
    proof = 'v0.10.4-packed-raven-compass-class'
    baseline = 'proven-v0.10.4-raven-map-runtime'
    candidate = 'Completionist_V103_Veithurgard_Raven_01'
    candidate_hash = 'E15E6BC82AE2773E'
    compass_class = 'CompletionistRaven'
    compass_class_hash = '5DC46967D3095F7E'
    compass_class_root = '0x4E2C50'
    candidate_wad_sha256 = $patchedHashes['wad_r_perm.dcb']
    baseline_hashes = $baselineHashes
    # Kept for compatibility with older rollback tooling; mapmaster here is a
    # v0.10.4 baseline, not literal retail stock.
    stock_hashes = $baselineHashes
    patched_hashes = $patchedHashes
    map_before = $mapBefore
    map_after = $mapAfter
    mapmaster_preserved = $true
    calls_show_on_install = $false
    writes_progression_state = $false
    writes_marker_state = $false
    installed_utc = [DateTime]::UtcNow.ToString('o')
}
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 6), $utf8)

try {
    foreach ($name in $patchedSources.Keys) {
        $target = Join-Path $dcbDir $name
        Copy-Item -LiteralPath $patchedSources[$name] -Destination $target -Force
        if ((Hash-File $target) -ne $patchedHashes[$name]) { throw "Installed hash mismatch for $name" }
    }
    if ((Hash-File (Join-Path $dcbDir 'mapmaster.dcb')) -ne $baselineHashes['mapmaster.dcb']) {
        throw 'mapmaster.dcb changed during proof install; refusing to continue.'
    }
} catch {
    try {
        $recovery = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        Restore-Proof $recovery
    } catch {
        Write-Warning "Automatic recovery also failed: $($_.Exception.Message)"
    }
    throw
}

Write-Host ''
Write-Host 'Completionist Map v0.10.4 PACKED Raven compass-class proof installed.'
Write-Host '- proven v0.10.4 mapmaster preserved unchanged'
Write-Host '- proven Raven map icon/binding preserved'
Write-Host '- native Raven coordinate/graph copies restored for runtime navigation'
Write-Host '- CompletionistRaven is at packed type-0x11E root 0x4E2C50'
Write-Host '- its visual fields intentionally clone DockPoint for this registration-only proof'
Write-Host '- Add to Compass calls ShowMarker(RavenID, CompletionistRaven) only when you press the map action'
Write-Host '- installer itself never calls ShowMarker and never writes save/progression/marker state'
Write-Host ''
Write-Host 'Launch GoW, load Veithurgard, open the map, select the Raven and press Add to Compass once.'
Write-Host 'If the request succeeds, return to gameplay and confirm the native compass/world marker and distance.'
Write-Host 'Then close GoW and run collect-packed-raven-compass-class-proof.ps1.'
Write-Host ("Emergency rollback: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
