[CmdletBinding()]
param(
    [string]$ExpectedBranch = 'codex/collectible-legendary-chests'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    throw 'Not inside the Completionist Map repository.'
}
Set-Location $RepoRoot

$branch = (& git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) {
    throw "Wrong branch '$branch'; expected '$ExpectedBranch'."
}

if (@(& git diff --cached --name-only).Count -gt 0) {
    throw 'Pre-existing staged changes exist; capture refused.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

$Capture = Join-Path $RepoRoot 'tools\v0.10.5\capture-legendary-current-states-readonly.py'
$Catalogue = Join-Path $RepoRoot 'config\collectibles\v0.10.5\all-collectibles.json'
$RavenGuard = Join-Path $RepoRoot 'tools\v0.10.5\test-raven-frozen-baseline.ps1'

foreach ($path in @($Capture, $Catalogue, $RavenGuard)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required file: $path"
    }
}

& pwsh -NoProfile -ExecutionPolicy Bypass -File $RavenGuard
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven baseline guard failed.' }

$gow = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') })
if ($gow.Count -ne 1) {
    throw 'Start God of War, load the save with an unopened tracked Legendary Chest nearby, then pause the game.'
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/legendary-open-state-before-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$console = Join-Path $outDir 'console-log.txt'
$resultFile = Join-Path $outDir 'result.txt'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$exitCode = 0
$failureMessage = ''
Start-Transcript -LiteralPath $console -Force | Out-Null
try {
    Write-Host 'LEGENDARY OPEN-STATE BEFORE CAPTURE - READ ONLY'
    Write-Host 'Game must be paused BEFORE opening the test Legendary Chest.'
    Write-Host 'This tool only reads staged checkpoint memory.'
    Write-Host ''

    & $python.Source $Capture --catalogue $Catalogue --output-dir $outDir
    $captureExit = $LASTEXITCODE
    if ($captureExit -ne 0) {
        throw "Legendary current-state capture failed with exit code $captureExit."
    }

    $reportPath = Join-Path $outDir 'report.json'
    if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) {
        throw 'Before capture returned no report.'
    }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json

    if ([int]$report.tracked_identity_count -ne 33) {
        throw "Expected 33 tracked identities; got $($report.tracked_identity_count)."
    }
    if ([int]$report.conflict_count -ne 0) {
        throw "Exact Legendary state conflicts detected: $($report.conflict_count)."
    }
    if ([int]$report.present_exact_state_count -lt 1) {
        throw 'No exact tracked Legendary state is currently staged. Move/load near a tracked Legendary Chest and retry.'
    }
    if ([bool]$report.safety.process_memory_written -or
        [bool]$report.safety.active_save_opened -or
        [bool]$report.safety.save_written_by_tooling -or
        [bool]$report.safety.progression_written_by_tooling -or
        [bool]$report.safety.game_files_written -or
        [bool]$report.safety.raven_runtime_modified) {
        throw 'Read-only safety contract changed.'
    }

    @(
        'result=LEGENDARY_OPEN_STATE_BEFORE_CAPTURED'
        'phase=before'
        "present_exact_state_count=$($report.present_exact_state_count)"
        "staged_record_count=$($report.snapshot.record_count)"
        'process_memory_written=false'
        'active_save_opened=false'
        'save_written_by_tooling=false'
        'progression_written_by_tooling=false'
        'game_files_written=false'
        'raven_runtime_modified=false'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
catch {
    $exitCode = 1
    $failureMessage = $_.Exception.Message
    @(
        'result=LEGENDARY_OPEN_STATE_BEFORE_FAILED'
        "reason=$failureMessage"
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
finally {
    Stop-Transcript | Out-Null
}

& git add -f -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git add before evidence failed' }

$message = if ($exitCode -eq 0) {
    "research(v0.10.5): capture Legendary open-state before $stamp"
} else {
    "research(v0.10.5): archive Legendary open-state before failure $stamp"
}
& git commit -m $message -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git commit before evidence failed' }
& git push origin $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push before evidence failed' }
$head = (& git rev-parse HEAD).Trim()

if ($exitCode -ne 0) {
    throw "Legendary before capture failed; evidence pushed in $head. $failureMessage"
}

Write-Host ''
Write-Host "LEGENDARY_OPEN_STATE_BEFORE_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
Write-Host ''
Write-Host 'NEXT GAMEPLAY ACTION:' -ForegroundColor Yellow
Write-Host '1. Resume the SAME save.'
Write-Host '2. Open EXACTLY ONE previously unopened tracked Legendary Chest.'
Write-Host '3. Do not open any other chest/collectible.'
Write-Host '4. Let the normal autosave/checkpoint finish.'
Write-Host '5. Pause the game without travelling/loading another area.'
Write-Host 'Then run the AFTER command I provide.'
