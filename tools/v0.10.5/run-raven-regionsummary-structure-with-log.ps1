param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/source-scans/raven-regionsummary-structure-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$jsonPath = Join-Path $logDir 'regionsummary-report.json'
$textPath = Join-Path $logDir 'regionsummary-report.txt'
$pythonOutput = Join-Path $logDir 'python-output.txt'
$published = $false
$transcriptStarted = $false

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Publish-Result([string]$Result) {
    if ($script:published) { return }
    $script:published = $true
    Stop-LocalTranscript

    @(
        "result=$Result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
        'scan_only=true'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8

    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git add of RegionSummary log directory failed.' }
    & git diff --cached --quiet -- $relativeLogDir
    if ($LASTEXITCODE -eq 0) { throw 'Nothing was staged for RegionSummary publication.' }
    if ($LASTEXITCODE -ne 1) { throw 'Unable to inspect staged RegionSummary output.' }

    & git commit -m "Archive Raven RegionSummary structure probe $stamp" -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git commit of RegionSummary output failed.' }
    & git push origin "HEAD:$expectedBranch"
    if ($LASTEXITCODE -ne 0) { throw 'git push of RegionSummary output failed.' }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map Raven RegionSummary native structure probe ==='
    Write-Host "Repository: $repo"
    Write-Host "Game root: $GameRoot"
    Write-Host 'Read-only native DCB analysis. Active saves are not opened and the game is not launched.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) {
        throw "Wrong branch. Expected '$expectedBranch', found '$branch'."
    }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) {
        throw "Refusing to run with pre-existing staged changes: $($staged -join ', ')"
    }

    $gow = Get-Process -Name 'GoW' -ErrorAction SilentlyContinue
    if ($null -ne $gow) {
        throw 'God of War is running. Close it before the native-data probe so source files stay frozen.'
    }

    if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
        throw "Game root not found: $GameRoot"
    }
    $quests = Join-Path $GameRoot 'exec\dc\pc_le\quests.dcb'
    $mapmaster = Join-Path $GameRoot 'exec\dc\pc_le\mapmaster.dcb'
    if (-not (Test-Path -LiteralPath $quests -PathType Leaf)) { throw "Missing quests.dcb: $quests" }
    if (-not (Test-Path -LiteralPath $mapmaster -PathType Leaf)) { throw "Missing mapmaster.dcb: $mapmaster" }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($null -eq $python) { throw 'Python executable not found on PATH.' }

    $analyzer = Join-Path $repo 'tools\v0.10.5\analyze-raven-regionsummary-structure.py'
    if (-not (Test-Path -LiteralPath $analyzer -PathType Leaf)) {
        throw "Analyzer missing: $analyzer"
    }

    & $python.Source $analyzer `
        --game-root $GameRoot `
        --output-json $jsonPath `
        --output-text $textPath 2>&1 | Tee-Object -FilePath $pythonOutput
    $scanExit = $LASTEXITCODE
    if ($scanExit -ne 0) {
        throw "RegionSummary analyzer exited with code $scanExit"
    }

    if (-not (Test-Path -LiteralPath $jsonPath -PathType Leaf)) { throw 'RegionSummary JSON report was not produced.' }
    if (-not (Test-Path -LiteralPath $textPath -PathType Leaf)) { throw 'RegionSummary text report was not produced.' }

    $report = Get-Content -LiteralPath $jsonPath -Raw | ConvertFrom-Json
    if ($report.status -ne 'EVIDENCE_ONLY') { throw "Unexpected report status: $($report.status)" }
    if ($report.safety.active_save_opened -ne $false) { throw 'Safety invariant failed: active_save_opened.' }
    if ($report.safety.game_written -ne $false) { throw 'Safety invariant failed: game_written.' }
    if ($report.safety.save_or_progression_written -ne $false) { throw 'Safety invariant failed: save_or_progression_written.' }
    if ($report.safety.game_launched -ne $false) { throw 'Safety invariant failed: game_launched.' }
    if ($report.safety.source_hashes_unchanged -ne $true) { throw 'Safety invariant failed: source hashes changed.' }

    Write-Host (
        'RAVEN_REGIONSUMMARY_STRUCTURE_PASSED ' +
        "parents=$($report.evidence_summary.raven_parent_records) " +
        "raven_named=$($report.evidence_summary.raven_named_quest_records) " +
        "direct_refs=$($report.evidence_summary.direct_parent_to_known_quest_refs) " +
        "array_child_candidates=$($report.evidence_summary.pointer_array_candidates_with_known_quest_elements)"
    )
    Write-Host 'active_save_opened=false game_written=false save_or_progression_written=false game_launched=false'

    Publish-Result 'SCAN_PASSED'
    Write-Host 'RAVEN_REGIONSUMMARY_STRUCTURE_PASSED_AND_PUSHED'
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "RAVEN_REGIONSUMMARY_STRUCTURE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try {
        Publish-Result 'SCAN_FAILED'
        Write-Host 'FAILED_REGIONSUMMARY_LOG_PUSHED'
    }
    catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host 'Only because publication failed, copy the console output manually.' -ForegroundColor Yellow
    }
    exit 1
}
finally {
    Stop-LocalTranscript
}
