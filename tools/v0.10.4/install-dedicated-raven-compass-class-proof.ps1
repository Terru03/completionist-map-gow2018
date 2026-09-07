param(
    [ValidateSet('Install', 'Remove')][string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'feat/v0.10.4-all-ravens') {
    throw "Expected feat/v0.10.4-all-ravens, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before installing or removing the v0.10.4 dedicated Raven class proof.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$dcbDir = Join-Path $game 'exec\dc\pc_le'
$mapTarget = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$stateDir = Join-Path $repo 'build\v0.10.4-dedicated-raven-runtime'
$backupDir = Join-Path $stateDir 'stock-backup'
$manifestPath = Join-Path $stateDir 'active.json'
$mapBackup = Join-Path $stateDir 'mapmenu-before.lua'
$prepReport = Join-Path $stateDir 'raven-dcb-prepared.json'
$classReport = Join-Path $stateDir 'compass-class-prepared.json'
$runtime3Dir = Join-Path $repo 'build\v0.10.3-native-runtime\game-root\exec\dc\pc_le'
$classOutput = Join-Path $repo 'build\v0.10.4-dedicated-raven-class\game-root\exec\dc\pc_le\wad_r_perm.dcb'
$prepareScript = Join-Path (Split-Path $PSScriptRoot -Parent) 'v0.10.3\prepare-native-raven-runtime.py'
$classBuilder = Join-Path $PSScriptRoot 'build-dedicated-raven-compass-class.py'
$bridge = Join-Path $PSScriptRoot 'dedicated-raven-compass-class.lua'
$utf8 = New-Object Text.UTF8Encoding($false)

$expectedExe = 'CAEBCB027980D7EAC9203D190F9EE649EEBC549F8DEFCE138E2114DC91F40452'
$stockHashes = [ordered]@{
    'mapmaster.dcb'    = 'AEC578E773898A1E60D5CCEDD0DF08E35B12AB54E4D26F4CD90740948430C2A0'
    'mapcoords.dcb'    = '5D0B7591032D7B56581A0D77946C3FAD4F0CBC1B9D245F3578407177C40BBE7D'
    'compassgraph.dcb' = 'C2FA6BAB0C7C1DBE413A41F477A5E01AB396731FC6F6D611047A8BD346A56C5E'
    'wad_r_perm.dcb'   = 'EABB9E548202E2F710520A0FAB905952CEFC10FFB2B6B5540E773D64EB1D8039'
}

function Hash-File([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Restore-Proof($Manifest) {
    foreach ($name in $stockHashes.Keys) {
        $target = Join-Path $dcbDir $name
        $backup = Join-Path $backupDir $name
        if (-not (Test-Path -LiteralPath $backup -PathType Leaf)) {
            throw "Missing DCB backup: $backup"
        }
        $stock = ([string]$Manifest.stock_hashes.$name).ToUpperInvariant()
        $patched = ([string]$Manifest.patched_hashes.$name).ToUpperInvariant()
        $current = Hash-File $target
        if ($current -ne $stock -and $current -ne $patched) {
            throw "$name changed after proof install. Refusing automatic overwrite. Backup preserved at $backup"
        }
        if ($current -ne $stock) {
            Copy-Item -LiteralPath $backup -Destination $target -Force
        }
        if ((Hash-File $target) -ne $stock) { throw "$name rollback hash mismatch." }
    }

    if (-not (Test-Path -LiteralPath $mapBackup -PathType Leaf)) { throw "Missing mapmenu backup: $mapBackup" }
    $mapStock = ([string]$Manifest.map_before).ToUpperInvariant()
    $mapPatched = ([string]$Manifest.map_after).ToUpperInvariant()
    $mapCurrent = Hash-File $mapTarget
    if ($mapCurrent -ne $mapStock -and $mapCurrent -ne $mapPatched) {
        throw 'mapmenu.lua changed after proof install. Refusing automatic overwrite.'
    }
    if ($mapCurrent -ne $mapStock) {
        Copy-Item -LiteralPath $mapBackup -Destination $mapTarget -Force
    }
    if ((Hash-File $mapTarget) -ne $mapStock) { throw 'mapmenu.lua rollback hash mismatch.' }
}

$exe = Join-Path $game 'GoW.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf) -or (Hash-File $exe) -ne $expectedExe) {
    throw 'GoW.exe differs from the researched build. Refusing dedicated Raven class proof.'
}

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'v0.10.4 dedicated Raven compass class proof is already removed.'
        return
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    Restore-Proof $manifest
    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'v0.10.4 dedicated Raven compass class proof removed.'
    Write-Host 'All four stock DCBs and mapmenu.lua were restored byte-for-byte.'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'v0.10.4 dedicated Raven compass class proof is already installed.'
}

$conflicting = @(
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
foreach ($path in @($mapTarget, $prepareScript, $classBuilder, $bridge)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing required file: $path" }
}
foreach ($name in $stockHashes.Keys) {
    $target = Join-Path $dcbDir $name
    if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Missing stock DCB: $target" }
    if ((Hash-File $target) -ne $stockHashes[$name]) {
        throw "$name is not the researched stock file. Refusing install."
    }
}

$mapSource = [IO.File]::ReadAllText($mapTarget)
if (-not $mapSource.Contains('[CompletionistMap v0.10.1] MAP_SCRIPT_LOADED')) {
    throw 'Expected tested Completionist map override was not found.'
}
if (-not $mapSource.Contains('function MapOn:ShowOnCompass(currState)')) {
    throw 'MapOn:ShowOnCompass missing from installed override.'
}
if ($mapSource.Contains('BEGIN COMPLETIONIST V0.10.4 DEDICATED RAVEN COMPASS CLASS')) {
    throw 'Dedicated Raven class bridge already appears in mapmenu.lua.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null

Write-Host 'Preparing the tested Raven marker/coordinate/graph DCBs...'
& $python.Source $prepareScript --game-root $game --repo-root $repo --output $prepReport
if ($LASTEXITCODE -ne 0) { throw 'Raven native DCB preparation failed.' }
$prep = Get-Content -LiteralPath $prepReport -Raw | ConvertFrom-Json
if ($prep.result -ne 'RUNTIME_DCB_COPIES_PREPARED_NOT_INSTALLED' -or
    [int]$prep.runtime_init_state -ne 0 -or
    $prep.game_files_written -ne $false -or
    $prep.compass_show_called -ne $false) {
    throw 'Prepared Raven DCB report failed safety checks.'
}

Write-Host 'Building the independent CompletionistRaven CompassIconClass copy...'
New-Item -ItemType Directory -Force -Path (Split-Path $classOutput -Parent) | Out-Null
& $python.Source $classBuilder --game-root $game --output $classOutput --report $classReport
if ($LASTEXITCODE -ne 0) { throw 'Dedicated Raven CompassIconClass build failed.' }
$class = Get-Content -LiteralPath $classReport -Raw | ConvertFrom-Json
if ($class.result -ne 'OFFLINE_COMPLETIONIST_RAVEN_COMPASS_CLASS_BUILT' -or
    $class.game_files_written -ne $false -or
    $class.installed -ne $false -or
    [string]$class.new_class.name -ne 'CompletionistRaven' -or
    [string]$class.new_class.uid -ne '5DC46967D3095F7E' -or
    $class.new_class.record_bytes_equal_dockpoint -ne $true) {
    throw 'Dedicated Raven class build report failed safety checks.'
}

$patchedSources = [ordered]@{
    'mapmaster.dcb'    = Join-Path $runtime3Dir 'mapmaster.dcb'
    'mapcoords.dcb'    = Join-Path $runtime3Dir 'mapcoords.dcb'
    'compassgraph.dcb' = Join-Path $runtime3Dir 'compassgraph.dcb'
    'wad_r_perm.dcb'   = $classOutput
}
$patchedHashes = [ordered]@{}
foreach ($name in $patchedSources.Keys) {
    $source = $patchedSources[$name]
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Prepared file missing: $source" }
    $patchedHashes[$name] = Hash-File $source
    if ($patchedHashes[$name] -eq $stockHashes[$name]) { throw "$name patched copy unexpectedly equals stock." }
}

if (Test-Path -LiteralPath $backupDir) { Remove-Item -LiteralPath $backupDir -Recurse -Force }
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
foreach ($name in $stockHashes.Keys) {
    $target = Join-Path $dcbDir $name
    $backup = Join-Path $backupDir $name
    Copy-Item -LiteralPath $target -Destination $backup -Force
    if ((Hash-File $backup) -ne $stockHashes[$name]) { throw "Backup hash mismatch for $name" }
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
    proof = 'v0.10.4-dedicated-raven-compass-class'
    candidate = 'Completionist_V103_Veithurgard_Raven_01'
    candidate_hash = 'E15E6BC82AE2773E'
    compass_class = 'CompletionistRaven'
    compass_class_hash = '5DC46967D3095F7E'
    stock_hashes = $stockHashes
    patched_hashes = $patchedHashes
    map_before = $mapBefore
    map_after = $mapAfter
    calls_show_on_install = $false
    writes_progression_state = $false
    installed_utc = [DateTime]::UtcNow.ToString('o')
}
[IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 6), $utf8)

try {
    foreach ($name in $patchedSources.Keys) {
        $target = Join-Path $dcbDir $name
        Copy-Item -LiteralPath $patchedSources[$name] -Destination $target -Force
        if ((Hash-File $target) -ne $patchedHashes[$name]) { throw "Installed hash mismatch for $name" }
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
Write-Host 'Completionist Map v0.10.4 dedicated Raven compass class proof installed.'
Write-Host '- Raven native marker remains InitState=0 and keeps its tested authored coordinates/graph edge'
Write-Host '- CompletionistRaven is a separate native CompassIconClass export'
Write-Host '- its visual fields intentionally clone DockPoint for this first runtime proof'
Write-Host '- Add to Compass will call ShowMarker(RavenID, CompletionistRaven) only when you press the map action'
Write-Host '- installer itself never calls ShowMarker and never changes progression/save state'
Write-Host ''
Write-Host 'Launch the game, open Midgard map, select the Veithurgard Raven, and press Add to Compass once.'
Write-Host 'If the HUD marker and distance appear normally, close the game and run the collector.'
Write-Host ("Emergency rollback: powershell -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
