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
if (@(& git diff --cached --name-only).Count -gt 0) { throw 'Pre-existing staged changes exist; capture refused.' }

& git pull --ff-only origin $branch | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Branch pull failed.' }

$alive = Join-Path $FrozenRoot 'alive\863677734\game.sav'
$dead = Join-Path $FrozenRoot 'dead\863677734\game.sav'
$scriptPath = Join-Path $repo 'tools\v0.10.5\analyze-raven-raw-slot-structural-shift.py'
foreach ($path in @($alive, $dead, $scriptPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/save-captures/gow-raven-raw-slot-structural-shift-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$pythonLog = Join-Path $logDir 'python-output.txt'
$jsonPath = Join-Path $logDir 'structural-shift.json'
$resultPath = Join-Path $logDir 'result.txt'

$published = $false
$transcriptStarted = $false
$succeeded = $false

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Publish-Capture {
    if ($script:published) { return }
    $script:published = $true
    Stop-LocalTranscript
    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage analysis directory.' }
    $staged = @(& git diff --cached --name-only --)
    foreach ($path in $staged) {
        if ($path -notlike "$relativeLogDir/*") { throw "Unexpected staged path outside analysis: $path" }
    }
    if ($staged.Count -gt 0) {
        $message = if ($script:succeeded) { 'Archive Raven raw slot structural shift analysis' } else { 'Archive Raven raw slot structural shift analysis failure' }
        & git commit -m $message -- $relativeLogDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Analysis commit failed.' }
        & git push origin "HEAD:$branch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Analysis push failed.' }
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true
    Write-Host '=== Raven raw-slot structural-shift analysis ==='
    Write-Host 'Offline/read-only. No game launch, no active-save reads, no source writes.'

    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & python $scriptPath --alive $alive --dead $dead --output-json $jsonPath --summary $resultPath 2>&1 |
            ForEach-Object {
                $line = [string]$_
                Add-Content -LiteralPath $pythonLog -Value $line -Encoding UTF8
                Write-Host $line
            }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $saved
    }
    if ($exitCode -ne 0) { throw "Structural-shift analyzer failed with exit code $exitCode." }
    if (-not (Test-Path -LiteralPath $jsonPath -PathType Leaf)) { throw 'Analyzer produced no JSON.' }

    $succeeded = $true
    Publish-Capture
    Write-Host 'RAVEN_RAW_SLOT_STRUCTURAL_SHIFT_ARCHIVED' -ForegroundColor Green
}
catch {
    $failure = $_.Exception.ToString()
    $failure | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8
    if (-not (Test-Path -LiteralPath $resultPath)) {
        @(
            'RAVEN_RAW_SLOT_STRUCTURAL_SHIFT_FAILED'
            "failure=$($failure -replace "`r?`n", ' | ')"
            'active_save_opened=false'
            'raw_save_bytes_emitted=false'
        ) | Set-Content -LiteralPath $resultPath -Encoding UTF8
    }
    Write-Host "RAVEN_RAW_SLOT_STRUCTURAL_SHIFT_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Capture } catch { Write-Host "ANALYSIS_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    Stop-LocalTranscript
}
