param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War completely before collecting the successful stock-art custom-class A/B.'
}

function Hash-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

$game = [IO.Path]::GetFullPath($GameRoot)
$stockState = Join-Path $repo 'build\v0.10.4-raven-native-custom-class-stock-art-control\active.json'
$classState = Join-Path $repo 'build\v0.10.4-raven-native-custom-class-control\active.json'
if (-not (Test-Path -LiteralPath $stockState -PathType Leaf)) { throw 'Stock-art custom-class A/B is not active.' }
if (-not (Test-Path -LiteralPath $classState -PathType Leaf)) { throw 'Custom-class mapmenu control is not active.' }
$stock = Get-Content -LiteralPath $stockState -Raw | ConvertFrom-Json
$class = Get-Content -LiteralPath $classState -Raw | ConvertFrom-Json
if ([string]$stock.kind -ne 'completionist-v104-raven-native-custom-class-stock-art-control') { throw 'Unexpected stock-art manifest kind.' }
if ([string]$class.kind -ne 'completionist-v104-raven-native-custom-class-control') { throw 'Unexpected custom-class manifest kind.' }

$map = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$coords = Join-Path $game 'exec\dc\pc_le\mapcoords.dcb'
$graph = Join-Path $game 'exec\dc\pc_le\compassgraph.dcb'
$perm = Join-Path $game 'exec\dc\pc_le\wad_r_perm.dcb'
$wad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$log = Join-Path $game 'mods\loader_log.txt'

$actual = [ordered]@{
    mapmenu = Hash-File $map
    mapcoords = Hash-File $coords
    compassgraph = Hash-File $graph
    wad_r_perm = Hash-File $perm
    r_ui_wad = Hash-File $wad
}
if ($actual.mapmenu -ne ([string]$class.map_after_sha256).ToLowerInvariant()) { throw 'mapmenu.lua no longer matches CompletionistRaven ShowMarker control.' }
if ($actual.mapcoords -ne ([string]$stock.mapcoords_sha256).ToLowerInvariant()) { throw 'mapcoords.dcb changed from proven native-routing A/B.' }
if ($actual.compassgraph -ne ([string]$stock.compassgraph_sha256).ToLowerInvariant()) { throw 'compassgraph.dcb changed from proven native-routing A/B.' }
if ($actual.wad_r_perm -ne ([string]$stock.perm_after_sha256).ToLowerInvariant()) { throw 'wad_r_perm.dcb is not the successful stock-art custom-class candidate.' }
if ($actual.r_ui_wad -ne ([string]$stock.r_ui_wad_sha256).ToLowerInvariant()) { throw 'r_ui.wad changed during stock-art A/B.' }
if (-not (Test-Path -LiteralPath $log -PathType Leaf)) { throw "Missing loader log: $log" }

$all = @(Get-Content -LiteralPath $log | ForEach-Object { $_.TrimEnd() })
$native = @($all | Where-Object { $_.Contains('[CompletionistMap v0.10.3-native]') })
$showBefore = @($native | Where-Object { $_ -match 'NATIVE_RAVEN_SHOW stage=before' -and $_ -match 'markerType=CompletionistRaven' }).Count
$showOK = @($native | Where-Object { $_ -match 'NATIVE_RAVEN_SHOW stage=lua_return ok=true' }).Count
$verify = @($native | Where-Object { $_ -match 'NATIVE_RAVEN_VERIFY active=true' }).Count

$archiveDir = Join-Path $repo 'archive\field-logs'
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null
$outRel = 'archive/field-logs/completionist-v104-native-custom-class-stock-art-success.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

$report = [ordered]@{
    schema = 1
    result = 'CUSTOM_CLASS_STOCK_ART_NATIVE_ROUTE_SUCCESS'
    captured_utc = [DateTime]::UtcNow.ToString('o')
    marker = 'Completionist_V103_Veithurgard_Raven_01'
    marker_type = 'CompletionistRaven'
    field_observation = [ordered]@{
        crash = $false
        native_routing_pathfinding = 'working'
        native_distance = 'visible (5m in supplied screenshot)'
        compass_hud_art = 'DockPoint/boat dock'
        in_world_art = 'DockPoint/boat dock'
    }
    state = [ordered]@{
        mapmenu_sha256 = $actual.mapmenu
        mapcoords_sha256 = $actual.mapcoords
        compassgraph_sha256 = $actual.compassgraph
        wad_r_perm_sha256 = $actual.wad_r_perm
        r_ui_wad_sha256 = $actual.r_ui_wad
        stock_art_manifest = $stockState
        custom_class_manifest = $classState
    }
    runtime_log_counts = [ordered]@{
        custom_show_before = $showBefore
        show_return_ok = $showOK
        manager_verify = $verify
    }
    isolation = [ordered]@{
        completionist_class_registration_safe = $true
        native_mapcoords_compassgraph_safe = $true
        custom_enlarged_r_ui_wad_remained_installed = $true
        only_crash_state_delta_removed = 'CompletionistRaven.IconName custom Raven HUD binding in wad_r_perm.dcb; stock-art A/B restores DockPoint class record'
        raw_r_ui_wad_file_size_is_not_the_crash_trigger = $true
        remaining_suspect = 'goCompletionistRavenHUD IconName resource resolution/structure or renderer compatibility'
    }
    safety = [ordered]@{
        game_files_written_by_collector = $false
        saves_progression_marker_state_written = $false
        stock_art_ab_left_installed = $true
    }
}
$report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $out -Encoding UTF8

Write-Host 'CUSTOM_CLASS_STOCK_ART_NATIVE_ROUTE_SUCCESS'
Write-Host '- no crash: true'
Write-Host '- native routing/pathfinding: working'
Write-Host '- visible art: DockPoint'
Write-Host '- same custom r_ui.wad remained installed: true'
Write-Host '- file-size-only crash hypothesis: ruled out'
Write-Host ("- report: {0}" -f $out)

Push-Location $repo
try {
    git add -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    git diff --cached --check -- $outRel
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
    git diff --cached --quiet -- $outRel
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Success report unchanged; nothing to commit.'
    } else {
        git commit -m 'Archive custom Raven stock-art native route success' -- $outRel
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
        Write-Host "Pushed success evidence to $Remote/$branch"
    }
} finally {
    Pop-Location
}
