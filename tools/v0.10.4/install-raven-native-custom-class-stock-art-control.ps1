param(
    [ValidateSet('Install','Remove')][string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before installing or removing the Raven stock-art custom-class control.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$perm = Join-Path $game 'exec\dc\pc_le\wad_r_perm.dcb'
$wad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$coords = Join-Path $game 'exec\dc\pc_le\mapcoords.dcb'
$graph = Join-Path $game 'exec\dc\pc_le\compassgraph.dcb'
$map = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$classState = Join-Path $repo 'build\v0.10.4-raven-native-custom-class-control\active.json'
$stateDir = Join-Path $repo 'build\v0.10.4-raven-native-custom-class-stock-art-control'
$manifestPath = Join-Path $stateDir 'active.json'
$backup = Join-Path $stateDir 'wad_r_perm-before.dcb'
$candidate = Join-Path $stateDir 'wad_r_perm-stock-art.dcb'
$report = Join-Path $stateDir 'stock-art-control.json'
$builder = Join-Path $PSScriptRoot 'build-raven-native-custom-class-stock-art-control.py'

$expectedCurrentPerm = '7b4ebef237043e97822ffdfc2ba788b0414434514e9ead723622df0fc12a1961'
$expectedStockArtPerm = '7f63cdda05f2dee6d56c961687bfe38c705c59b4d5fa9158aa218b435b2ec83e'
$expectedWad = '5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60'
$expectedCoords = '945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb'
$expectedGraph = 'd0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68'
$expectedStock = 'eabb9e548202e2f710520a0fab905952cefc10ffb2b6b5540e773d64eb1d8039'

function Hash-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        Write-Host 'Raven stock-art custom-class control is already removed.'
        return
    }
    $m = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $current = Hash-File $perm
    $before = ([string]$m.perm_before_sha256).ToLowerInvariant()
    $after = ([string]$m.perm_after_sha256).ToLowerInvariant()
    if ($current -ne $before -and $current -ne $after) {
        throw 'wad_r_perm.dcb changed after stock-art control install. Refusing overwrite.'
    }
    if ((Hash-File $backup) -ne $before) { throw 'Stock-art control backup hash mismatch.' }
    if ($current -eq $after) {
        Copy-Item -LiteralPath $backup -Destination $perm -Force
    }
    if ((Hash-File $perm) -ne $before) { throw 'Stock-art control rollback hash mismatch.' }
    $removed = Join-Path $stateDir ('removed-' + [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Raven stock-art custom-class control removed. Dedicated Raven HUD DCB binding restored byte-for-byte.'
    Write-Host '- custom-class mapmenu control left installed: true'
    Write-Host '- native mapcoords/compassgraph A/B left installed: true'
    Write-Host '- r_ui.wad touched: false'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Raven stock-art custom-class control is already installed.'
}
if (-not (Test-Path -LiteralPath $classState -PathType Leaf)) {
    throw 'Custom-class mapmenu control is not active. This A/B requires the exact crashing CompletionistRaven ShowMarker state.'
}
$classManifest = Get-Content -LiteralPath $classState -Raw | ConvertFrom-Json
if ([string]$classManifest.kind -ne 'completionist-v104-raven-native-custom-class-control') {
    throw 'Unexpected custom-class control manifest kind.'
}
if ((Hash-File $map) -ne ([string]$classManifest.map_after_sha256).ToLowerInvariant()) {
    throw 'mapmenu.lua no longer matches the active custom-class control.'
}
if ((Hash-File $perm) -ne $expectedCurrentPerm) { throw 'wad_r_perm.dcb is not the crashing dedicated-HUD binding baseline.' }
if ((Hash-File $wad) -ne $expectedWad) { throw 'r_ui.wad changed from the crashing dedicated-HUD baseline.' }
if ((Hash-File $coords) -ne $expectedCoords) { throw 'Known-good Raven mapcoords A/B is not installed.' }
if ((Hash-File $graph) -ne $expectedGraph) { throw 'Known-good Raven compassgraph A/B is not installed.' }
if (-not (Test-Path -LiteralPath $builder -PathType Leaf)) { throw "Missing stock-art builder: $builder" }
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }

$stockCandidates = @()
$backupRoot = Join-Path $repo 'build\v0.10.4\raven-compass-hud-four-payload\runtime-install-backups'
if (Test-Path -LiteralPath $backupRoot -PathType Container) {
    Get-ChildItem -LiteralPath $backupRoot -Recurse -Filter 'wad_r_perm.dcb.before-raven-hud' -File | ForEach-Object {
        if ((Hash-File $_.FullName) -eq $expectedStock) { $stockCandidates += $_.FullName }
    }
}
if ($stockCandidates.Count -ne 1) {
    throw "Expected exactly one exact pre-HUD stock DCB backup, found $($stockCandidates.Count)."
}
$stock = $stockCandidates[0]

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
Copy-Item -LiteralPath $perm -Destination $backup -Force
if ((Hash-File $backup) -ne $expectedCurrentPerm) { throw 'Live dedicated-HUD DCB backup verification failed.' }

& $python.Source $builder --stock $stock --output $candidate --report $report
if ($LASTEXITCODE -ne 0) { throw 'Stock-art custom-class candidate build failed.' }
if ((Hash-File $candidate) -ne $expectedStockArtPerm) { throw 'Stock-art candidate hash differs from runtime-proven packed class candidate.' }
$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'OFFLINE_RAVEN_NATIVE_CUSTOM_CLASS_STOCK_ART_CONTROL_BUILT' -or
    $proof.class_record_byte_identical_to_DockPoint -ne $true -or
    $proof.game_files_written -ne $false) {
    throw 'Stock-art candidate proof failed.'
}

$m = [ordered]@{
    kind = 'completionist-v104-raven-native-custom-class-stock-art-control'
    purpose = 'Isolate dedicated Raven HUD IconName/resource chain from custom class registration.'
    perm_before_sha256 = $expectedCurrentPerm
    perm_after_sha256 = $expectedStockArtPerm
    r_ui_wad_sha256 = $expectedWad
    mapcoords_sha256 = $expectedCoords
    compassgraph_sha256 = $expectedGraph
    mapmenu_sha256 = Hash-File $map
    custom_class_manifest = $classState
    stock_source = $stock
    backup = $backup
    candidate = $candidate
    report = $report
    only_wad_r_perm_written = $true
    installed_utc = [DateTime]::UtcNow.ToString('o')
}
$m | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

try {
    Copy-Item -LiteralPath $candidate -Destination $perm -Force
    if ((Hash-File $perm) -ne $expectedStockArtPerm) { throw 'Installed stock-art DCB hash mismatch.' }
} catch {
    Copy-Item -LiteralPath $backup -Destination $perm -Force
    if ((Hash-File $perm) -ne $expectedCurrentPerm) { throw 'Stock-art install failed and rollback verification also failed.' }
    Remove-Item -LiteralPath $manifestPath -Force -ErrorAction SilentlyContinue
    throw
}

Write-Host ''
Write-Host 'Raven CUSTOM CLASS + STOCK ART A/B installed.'
Write-Host '- ShowMarker class remains: CompletionistRaven'
Write-Host '- CompletionistRaven class record now byte-identical to DockPoint'
Write-Host '- native Raven mapcoords/compassgraph: unchanged and previously proven working'
Write-Host '- current r_ui.wad: unchanged'
Write-Host '- game file changed by this A/B: wad_r_perm.dcb only'
Write-Host '- saves/progression/marker state touched: false'
Write-Host ''
Write-Host 'Launch God of War and Add the same Raven to Compass.'
Write-Host 'Expected if dedicated HUD binding caused the crash: NO crash, native routing works, DockPoint art renders.'
Write-Host 'If it still crashes, the cause is broader than CompletionistRaven.IconName alone.'
Write-Host ''
Write-Host ("Rollback: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
