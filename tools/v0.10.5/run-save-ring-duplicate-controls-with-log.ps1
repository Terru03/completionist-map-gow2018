param()

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

$documents = [Environment]::GetFolderPath('MyDocuments')
if ([string]::IsNullOrWhiteSpace($documents) -or -not (Test-Path -LiteralPath $documents -PathType Container)) {
    throw "Documents folder unavailable: $documents"
}

$pairRoot = Get-ChildItem -LiteralPath $documents -Directory -Filter 'GodOfWar-RavenAliveDead-*' |
    Sort-Object Name -Descending |
    Where-Object {
        (Get-ChildItem -LiteralPath (Join-Path $_.FullName 'alive') -Filter 'game.sav' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1) -and
        (Get-ChildItem -LiteralPath (Join-Path $_.FullName 'dead') -Filter 'game.sav' -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1)
    } |
    Select-Object -First 1
if ($null -eq $pairRoot) { throw 'No frozen GodOfWar-RavenAliveDead-* pair with alive/dead game.sav files found.' }

$alive = Get-ChildItem -LiteralPath (Join-Path $pairRoot.FullName 'alive') -Filter 'game.sav' -File -Recurse | Select-Object -First 1
$dead = Get-ChildItem -LiteralPath (Join-Path $pairRoot.FullName 'dead') -Filter 'game.sav' -File -Recurse | Select-Object -First 1
if ($null -eq $alive -or $null -eq $dead) { throw 'Target frozen pair is incomplete.' }

$scriptPath = Join-Path $repo 'tools\v0.10.5\analyze-save-ring-duplicate-controls.py'
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { throw "Analyzer missing: $scriptPath" }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/save-captures/gow-save-ring-duplicate-controls-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$pythonLog = Join-Path $logDir 'python-output.txt'
$jsonPath = Join-Path $logDir 'duplicate-controls.json'
$summaryPath = Join-Path $logDir 'result.txt'
$transcriptStarted = $false
$succeeded = $false
$published = $false

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Publish-Analysis {
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
        $message = if ($script:succeeded) { 'Archive frozen save ring duplicate controls' } else { 'Archive frozen save ring duplicate controls failure' }
        & git commit -m $message -- $relativeLogDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Analysis commit failed.' }
        & git push origin "HEAD:$branch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Analysis push failed.' }
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true
    Write-Host '=== Frozen GoW save-ring duplicate controls ==='
    Write-Host "Documents root: $documents"
    Write-Host "Target frozen pair: $($pairRoot.FullName)"
    Write-Host "ALIVE: $($alive.FullName)"
    Write-Host "DEAD:  $($dead.FullName)"
    Write-Host 'Offline/read-only. Active saves are refused by the Python analyzer.'

    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & python $scriptPath `
            --root $documents `
            --target-alive $alive.FullName `
            --target-dead $dead.FullName `
            --output-json $jsonPath `
            --summary $summaryPath 2>&1 |
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
    if ($exitCode -ne 0) { throw "Duplicate-control analyzer failed with exit code $exitCode." }
    if (-not (Test-Path -LiteralPath $jsonPath -PathType Leaf)) { throw 'Analyzer produced no JSON.' }
    if (-not (Test-Path -LiteralPath $summaryPath -PathType Leaf)) { throw 'Analyzer produced no summary.' }

    $succeeded = $true
    Publish-Analysis
    Write-Host 'SAVE_RING_DUPLICATE_CONTROLS_ARCHIVED' -ForegroundColor Green
}
catch {
    $failure = $_.Exception.ToString()
    $failure | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8
    if (-not (Test-Path -LiteralPath $summaryPath -PathType Leaf)) {
        @(
            'SAVE_RING_DUPLICATE_CONTROLS_FAILED'
            "timestamp=$(Get-Date -Format o)"
            "failure=$($failure -replace "`r?`n", ' | ')"
            'active_save_opened=false'
            'raw_save_bytes_emitted=false'
        ) | Set-Content -LiteralPath $summaryPath -Encoding UTF8
    }
    Write-Host "SAVE_RING_DUPLICATE_CONTROLS_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Analysis } catch { Write-Host "ANALYSIS_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    Stop-LocalTranscript
}
