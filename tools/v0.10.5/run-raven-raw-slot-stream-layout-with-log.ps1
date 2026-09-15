param(
    [string]$FrozenRoot = 'C:\Users\david\Documents\GodOfWar-RavenAliveDead-20260915-220250'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$branch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Run from inside completionist-map-gow2018 repository.' }
Set-Location $repo
$current = (& git branch --show-current).Trim()
if ($current -ne $branch) { throw "Wrong branch. Expected '$branch', found '$current'." }
if (@(& git diff --cached --name-only).Count -gt 0) { throw 'Pre-existing staged changes exist; analysis refused.' }

& git pull --ff-only origin $branch | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Branch pull failed.' }

$alive = Join-Path $FrozenRoot 'alive\863677734\game.sav'
$dead = Join-Path $FrozenRoot 'dead\863677734\game.sav'
$script = Join-Path $repo 'tools\v0.10.5\analyze-raven-raw-slot-stream-layout.py'
foreach ($path in @($alive,$dead,$script)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relative = "archive/field-logs/save-captures/gow-raven-raw-slot-stream-layout-$stamp"
$out = Join-Path $repo $relative
New-Item -ItemType Directory -Force -Path $out | Out-Null
$json = Join-Path $out 'stream-layout.json'
$summary = Join-Path $out 'result.txt'
$console = Join-Path $out 'console-log.txt'

$transcriptStarted = $false
$succeeded = $false
$published = $false

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Publish-Result {
    if ($script:published) { return }
    $script:published = $true
    Stop-LocalTranscript
    & git add -- $relative
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage analysis directory.' }
    $staged = @(& git diff --cached --name-only --)
    foreach ($path in $staged) {
        if ($path -notlike "$relative/*") { throw "Unexpected staged path outside analysis: $path" }
    }
    if ($staged.Count -gt 0) {
        $message = if ($script:succeeded) { 'Archive Raven raw slot stream layout analysis' } else { 'Archive Raven raw slot stream layout analysis failure' }
        & git commit -m $message -- $relative | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Analysis commit failed.' }
        & git push origin "HEAD:$branch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Analysis push failed.' }
    }
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcriptStarted = $true
    Write-Host '=== Raven raw-slot stream-layout classification ==='
    Write-Host 'Offline/read-only. No game launch, no active-save reads, no source writes.'

    & python $script --alive $alive --dead $dead --alive-slot 5 --dead-slot 17 --output $json --summary $summary
    if ($LASTEXITCODE -ne 0) { throw "Analyzer failed with exit code $LASTEXITCODE" }
    if (-not (Test-Path -LiteralPath $json -PathType Leaf)) { throw 'Analyzer produced no JSON.' }

    $succeeded = $true
    Publish-Result
    Write-Host 'RAVEN_RAW_SLOT_STREAM_LAYOUT_ARCHIVED' -ForegroundColor Green
}
catch {
    $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $out 'error.txt') -Encoding UTF8
    Write-Host "RAVEN_RAW_SLOT_STREAM_LAYOUT_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Result } catch { Write-Host "ANALYSIS_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    Stop-LocalTranscript
}
