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

foreach ($path in @($loaderLog, $mapLua, $eventLua)) {
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
    $_ -like '*[CompletionistMap v0.10.5-all-ravens]*' -or
    $_ -like '*[CompletionistMap v0.10.5-raven-events]*'
})
$completionist | Set-Content -LiteralPath (Join-Path $outDir 'completionist-extract.txt') -Encoding UTF8

$interesting = @($lines | Where-Object {
    $_ -match '(?i)(completionist|lua|error|exception|failed|assert|precisionchallenge|mapmenu)'
})
$interesting | Select-Object -Last 800 | Set-Content -LiteralPath (Join-Path $outDir 'interesting-tail.txt') -Encoding UTF8

$mapApi = @($completionist | Where-Object { $_ -like '*v0.10.5-all-ravens* API *' }).Count
$eventApi = @($completionist | Where-Object { $_ -like '*v0.10.5-raven-events* API *' }).Count
$persisted = @($completionist | Where-Object { $_ -like '* PERSISTED_SCAN*' -or $_ -like '* PERSISTED_SCAN_REFUSED*' })
$states = @($completionist | Where-Object { $_ -like '* v0.10.5-all-ravens* STATE *' })
$eventRefused = @($completionist | Where-Object { $_ -like '*v0.10.5-raven-events* STATE_REFUSED *' })
$eventScheduleFailures = @($completionist | Where-Object { $_ -like '*v0.10.5-raven-events* SCHEDULE_FAILED *' })

$mapText = Read-SharedText $mapLua
$eventText = Read-SharedText $eventLua
$result = [ordered]@{
    schema = 1
    captured_utc = (Get-Date).ToUniversalTime().ToString('o')
    branch = $branch
    game_root = $GameRoot
    game_running = [bool](@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0)
    files = [ordered]@{
        mapmenu_sha256 = Sha256 $mapLua
        precisionchallenge_sha256 = Sha256 $eventLua
        map_runtime_marker_present = $mapText.Contains('BEGIN COMPLETIONIST V0.10.5 ALL RAVENS')
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
