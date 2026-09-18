param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeDir = "archive/field-logs/runtime-captures/all-ravens-state-$stamp"
$outDir = Join-Path $repo $relativeDir
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$loaderLog = Join-Path $GameRoot 'mods\loader_log.txt'
$mapLua = Join-Path $GameRoot 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$hudLua = Join-Path $GameRoot 'mods\lua\gameart\ui\scripts\hud\mainhud.lua'
$coreSaveLua = Join-Path $GameRoot 'mods\lua\gameart\scripts\libraries\core\save.lua'
$eventLua = Join-Path $GameRoot 'mods\lua\gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
$activeManifest = Join-Path $repo 'build\v0.10.5-all-ravens-runtime-test\transaction\active.json'

function Read-SharedText([string]$Path) {
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    try {
        $reader = New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8, $true)
        try { return $reader.ReadToEnd() }
        finally { $reader.Dispose() }
    }
    finally { $stream.Dispose() }
}

function Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

$branch = (& git branch --show-current).Trim()
if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }

foreach ($path in @($loaderLog, $mapLua, $hudLua, $coreSaveLua, $eventLua)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing file: $path" }
}

$logText = Read-SharedText $loaderLog
[IO.File]::WriteAllText(
    (Join-Path $outDir 'loader_log.txt'),
    $logText,
    (New-Object Text.UTF8Encoding($false))
)

$lines = @($logText -split "\r?\n")
$completionist = @($lines | Where-Object {
    $_ -like '*CompletionistMap v0.10.5-all-ravens*' -or
    $_ -like '*CompletionistMap v0.10.5-raven-events*' -or
    $_ -like '*CompletionistMap v0.10.5-raven-ui-bridge*' -or
    $_ -like '*CompletionistMap v0.10.5-raven-cache*'
})
$completionist | Set-Content -LiteralPath (Join-Path $outDir 'completionist-extract.txt') -Encoding UTF8

$interesting = @($lines | Where-Object {
    $_ -match '(?i)(completionist|lua|error|exception|failed|assert|precisionchallenge|mapmenu)'
})
$interesting | Select-Object -Last 800 | Set-Content -LiteralPath (Join-Path $outDir 'interesting-tail.txt') -Encoding UTF8

$mapApi = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-all-ravens\] API ' }).Count
$eventApi = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-events\] API ' }).Count
$persisted = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-all-ravens\] PERSISTED_SCAN(_REFUSED)? ' })
$states = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-all-ravens\] STATE ' })
$eventRefused = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-events\] STATE_REFUSED ' })
$eventScheduleFailures = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-events\] SCHEDULE_FAILED ' })
$stateSends = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-events\] STATE_SEND ' })
$exactHides = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-events\] EXACT_HIDE ' })
$bridgeApi = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-ui-bridge\] API ' })
$bridgeReceives = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-ui-bridge\] RECV ' })
$bridgeRefused = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-ui-bridge\] RECV_REFUSED ' })
$uiBootstrap = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-all-ravens\] UI_STATE_BOOTSTRAP ' })
$cacheApi = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-cache\] API ' })
$cacheUpdates = @($completionist | Where-Object {
    $_ -match '\[CompletionistMap v0\.10\.5-raven-cache\] UPDATE ' -or
    $_ -match '\[CompletionistMap v0\.10\.5-raven-events\] CACHE_UPDATE '
})
$cacheReplays = @($completionist | Where-Object {
    $_ -match '\[CompletionistMap v0\.10\.5-raven-cache\] RESTORE_REPLAY ' -or
    $_ -match '\[CompletionistMap v0\.10\.5-raven-events\] CACHE_REPLAY '
})
$cacheReceives = @($completionist | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-ui-bridge\] CACHE_RECV ' })
$cacheRefused = @($completionist | Where-Object { $_ -match 'CACHE_(RECV_)?REFUSED ' })

$mapText = Read-SharedText $mapLua
$hudText = Read-SharedText $hudLua
$coreSaveText = Read-SharedText $coreSaveLua
$eventText = Read-SharedText $eventLua
$result = [ordered]@{
    schema = 1
    captured_utc = (Get-Date).ToUniversalTime().ToString('o')
    branch = $branch
    game_root = $GameRoot
    game_running = [bool](@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0)
    files = [ordered]@{
        mapmenu_sha256 = Sha256 $mapLua
        mainhud_sha256 = Sha256 $hudLua
        core_save_sha256 = Sha256 $coreSaveLua
        precisionchallenge_sha256 = Sha256 $eventLua
        map_runtime_marker_present = $mapText.Contains('BEGIN COMPLETIONIST V0.10.5 ALL RAVENS')
        hud_receiver_marker_present = $hudText.Contains('BEGIN COMPLETIONIST V0.10.5 ALL RAVEN UI STATE RECEIVER')
        checkpoint_cache_marker_present = $coreSaveText.Contains('BEGIN COMPLETIONIST V0.10.5 RAVEN CHECKPOINT CACHE')
        event_runtime_marker_present = $eventText.Contains('BEGIN COMPLETIONIST V0.10.5 ALL RAVEN EVENTS')
    }
    log = [ordered]@{
        completionist_line_count = $completionist.Count
        map_api_lines = $mapApi
        event_api_lines = $eventApi
        persisted_scan_lines = $persisted.Count
        state_publish_lines = $states.Count
        event_refused_lines = $eventRefused.Count
        schedule_failure_lines = $eventScheduleFailures.Count
        state_send_lines = $stateSends.Count
        exact_hide_lines = $exactHides.Count
        bridge_api_lines = $bridgeApi.Count
        bridge_receive_lines = $bridgeReceives.Count
        bridge_refused_lines = $bridgeRefused.Count
        ui_state_bootstrap_lines = $uiBootstrap.Count
        cache_api_lines = $cacheApi.Count
        cache_update_lines = $cacheUpdates.Count
        cache_restore_replay_lines = $cacheReplays.Count
        cache_receive_lines = $cacheReceives.Count
        cache_refused_lines = $cacheRefused.Count
    }
    read_only_capture = $true
    game_files_written = $false
    save_or_progression_written = $false
}
[IO.File]::WriteAllText(
    (Join-Path $outDir 'result.json'),
    (($result | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
    (New-Object Text.UTF8Encoding($false))
)

if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
    Copy-Item -LiteralPath $activeManifest -Destination (Join-Path $outDir 'active-transaction.json') -Force
}

& git add -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
& git commit -m "field: capture all-Ravens runtime state $stamp" -- $relativeDir | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
$commit = (& git rev-parse HEAD).Trim()
& git push origin "HEAD:$expectedBranch" | Out-Host
if ($LASTEXITCODE -ne 0) { throw "capture committed locally as $commit but push failed." }

Write-Host "ALL_RAVENS_RUNTIME_STATE_CAPTURED_AND_PUSHED $commit"
Write-Host "  completionist lines: $($completionist.Count)"
Write-Host "  map API lines: $mapApi"
Write-Host "  event API lines: $eventApi"
Write-Host "  persisted scan lines: $($persisted.Count)"
Write-Host "  state publish lines: $($states.Count)"
Write-Host "  event refused lines: $($eventRefused.Count)"
Write-Host "  state send lines: $($stateSends.Count)"
Write-Host "  bridge receive lines: $($bridgeReceives.Count)"
Write-Host "  exact hide lines: $($exactHides.Count)"
Write-Host "  UI state bootstrap lines: $($uiBootstrap.Count)"
Write-Host "  checkpoint cache update lines: $($cacheUpdates.Count)"
Write-Host "  checkpoint cache restore replay lines: $($cacheReplays.Count)"
Write-Host "  checkpoint cache receive lines: $($cacheReceives.Count)"
