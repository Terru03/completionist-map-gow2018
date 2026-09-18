[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

$branch = (& git branch --show-current).Trim()
if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }
if (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }) {
    throw 'Close God of War before running the checkpoint-cache diagnostic.'
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/raven-checkpoint-cache-diagnostic-$stamp"
$outDir = Join-Path $repo $relativeDir
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$loaderLog = Join-Path $GameRoot 'mods\loader_log.txt'
$scanner = Join-Path $repo 'tools\v0.10.5\diagnose-raven-checkpoint-cache-save.py'
$saveJson = Join-Path $outDir 'active-save-cache-scan.json'
$cacheLog = Join-Path $outDir 'cache-runtime-extract.txt'
$resultJson = Join-Path $outDir 'result.json'
$activeManifest = Join-Path $repo 'build\v0.10.5-all-ravens-runtime-test\transaction\active.json'

if (-not (Test-Path -LiteralPath $loaderLog -PathType Leaf)) { throw "Missing loader log: $loaderLog" }
if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) { throw "Missing scanner: $scanner" }

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command py -ErrorAction Stop }

if ($python.Name -eq 'py.exe' -or $python.Name -eq 'py') {
    & $python.Source -3 $scanner --output $saveJson
}
else {
    & $python.Source $scanner --output $saveJson
}
if ($LASTEXITCODE -ne 0) { throw "Save scanner failed with exit code $LASTEXITCODE" }

$lines = Get-Content -LiteralPath $loaderLog -ErrorAction Stop
$interesting = @($lines | Where-Object {
    $_ -like '*CompletionistMap v0.10.5-raven-cache*' -or
    $_ -like '*CompletionistMap v0.10.5-raven-events*STATE_SEND*' -or
    $_ -like '*CompletionistMap v0.10.5-raven-ui-bridge*CACHE_*' -or
    $_ -like '*CompletionistMap v0.10.5-all-ravens*UI_STATE_BOOTSTRAP*'
})
$interesting | Set-Content -LiteralPath $cacheLog -Encoding UTF8

$scan = Get-Content -LiteralPath $saveJson -Raw | ConvertFrom-Json
$cacheApi = @($interesting | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-cache\] API ' })
$cacheUpdates = @($interesting | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-cache\] UPDATE ' })
$cacheReplays = @($interesting | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-cache\] RESTORE_REPLAY ' })
$stateSends = @($interesting | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-events\] STATE_SEND ' })
$stateSendCacheTrue = @($stateSends | Where-Object { $_ -match 'checkpointCacheUpdated=true' })
$stateSendCacheFalse = @($stateSends | Where-Object { $_ -match 'checkpointCacheUpdated=false' })
$cacheReceives = @($interesting | Where-Object { $_ -match '\[CompletionistMap v0\.10\.5-raven-ui-bridge\] CACHE_RECV ' })
$cacheRefused = @($interesting | Where-Object { $_ -match 'CACHE_(RECV_)?REFUSED ' })

$result = [ordered]@{
    schema = 1
    captured_utc = (Get-Date).ToUniversalTime().ToString('o')
    branch = $expectedBranch
    repo_head = (& git rev-parse HEAD).Trim()
    game_closed = $true
    active_save_cache_present = [bool]$scan.cache_present_any
    runtime = [ordered]@{
        cache_api_lines = $cacheApi.Count
        cache_update_lines = $cacheUpdates.Count
        cache_restore_replay_lines = $cacheReplays.Count
        state_send_lines = $stateSends.Count
        state_send_cache_updated_true = $stateSendCacheTrue.Count
        state_send_cache_updated_false = $stateSendCacheFalse.Count
        cache_receive_lines = $cacheReceives.Count
        cache_refused_lines = $cacheRefused.Count
    }
    active_transaction = if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
        Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    } else { $null }
    save_or_progression_written_by_diagnostic = $false
}
[IO.File]::WriteAllText(
    $resultJson,
    (($result | ConvertTo-Json -Depth 12) + [Environment]::NewLine),
    (New-Object Text.UTF8Encoding($false))
)

& git add -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
& git commit -m "diag(v0.10.5): capture failed Raven checkpoint-cache persistence $stamp" -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
& git push origin $expectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }

Write-Host "RAVEN_CHECKPOINT_CACHE_DIAGNOSTIC_PUSHED $((& git rev-parse HEAD).Trim())"
Write-Host "  active save cache present: $([bool]$scan.cache_present_any)"
Write-Host "  cache UPDATE lines: $($cacheUpdates.Count)"
Write-Host "  state sends cacheUpdated=true/false: $($stateSendCacheTrue.Count)/$($stateSendCacheFalse.Count)"
Write-Host "  restore replay lines: $($cacheReplays.Count)"
Write-Host "  cache receive lines: $($cacheReceives.Count)"
