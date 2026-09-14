param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/source-scans/collectible-changed-stream-fingerprint-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$reportJson = Join-Path $logDir 'fingerprint-report.json'
$reportMd = Join-Path $logDir 'fingerprint-report.md'
$summaryPath = Join-Path $logDir 'summary.txt'
$pythonOutput = Join-Path $logDir 'python-output.txt'
$published = $false
$transcriptStarted = $false

function Resolve-FrozenGameSave([string]$BackupDir) {
    if (-not (Test-Path -LiteralPath $BackupDir -PathType Container)) {
        throw "Frozen backup directory missing: $BackupDir"
    }
    $matches = @(Get-ChildItem -LiteralPath $BackupDir -Recurse -File -Filter 'game.sav' -ErrorAction Stop)
    if ($matches.Count -ne 1) {
        throw "Expected exactly one game.sav below frozen backup '$BackupDir', found $($matches.Count)."
    }
    return $matches[0].FullName
}

function Publish-TraceLog([string]$Result) {
    if ($script:published) { return }
    $script:published = $true
    try {
        if ($script:transcriptStarted) {
            Stop-Transcript | Out-Null
            $script:transcriptStarted = $false
        }

        @(
            "result=$Result"
            "timestamp=$(Get-Date -Format o)"
            "branch=$expectedBranch"
            "active_save_opened=false"
            "game_written=false"
            "save_or_progression_written=false"
            "game_launched=false"
            "scan_only=true"
        ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8

        $allowed = @(
            'console-log.txt', 'fingerprint-report.json', 'fingerprint-report.md',
            'summary.txt', 'python-output.txt', 'result.txt', 'error.txt'
        )
        $unexpected = @(Get-ChildItem -LiteralPath $logDir -File | Where-Object { $_.Name -notin $allowed })
        if ($unexpected.Count -gt 0) {
            throw "Refusing to publish unexpected fingerprint-log files: $($unexpected.Name -join ', ')"
        }
        $saveCopies = @(Get-ChildItem -LiteralPath $logDir -Recurse -File -Filter '*.sav')
        if ($saveCopies.Count -gt 0) { throw 'Refusing to publish a copied save file.' }
        $oversized = @(Get-ChildItem -LiteralPath $logDir -File | Where-Object { $_.Length -gt 5MB })
        if ($oversized.Count -gt 0) {
            throw "Refusing to publish unexpectedly large fingerprint-log files: $($oversized.Name -join ', ')"
        }

        & git add -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git add of fingerprint trace log directory failed.' }

        $stagedNow = @(& git diff --cached --name-only)
        if ($LASTEXITCODE -ne 0) { throw 'Unable to verify staged fingerprint trace files.' }
        $prefix = ($relativeLogDir -replace '\\','/').TrimEnd('/') + '/'
        $foreign = @($stagedNow | Where-Object { -not (($_ -replace '\\','/').StartsWith($prefix)) })
        if ($foreign.Count -gt 0) {
            & git restore --staged -- $relativeLogDir 2>$null
            throw "Refusing to commit unrelated staged paths: $($foreign -join ', ')"
        }

        & git diff --cached --quiet -- $relativeLogDir
        if ($LASTEXITCODE -eq 0) { return }
        & git commit -m "Archive collectible changed-stream fingerprint $stamp" -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git commit of fingerprint trace log directory failed.' }
        & git push origin "HEAD:$expectedBranch"
        if ($LASTEXITCODE -ne 0) { throw 'git push of fingerprint trace log directory failed.' }
    }
    catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
        throw
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map collectible changed-stream semantic fingerprint ==='
    Write-Host "Repository: $repo"
    Write-Host 'Read-only frozen-backup scan. No game launch, active-save access, or progression writes.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) {
        throw "Wrong branch. Expected '$expectedBranch', found '$branch'."
    }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) {
        throw "Refusing to run with pre-existing staged changes: $($staged -join ', ')"
    }

    $gameProcess = @(Get-Process -Name 'GoW' -ErrorAction SilentlyContinue)
    if ($gameProcess.Count -gt 0) {
        throw 'God of War is running. Close it before the read-only forensic scan.'
    }

    $desktop = [Environment]::GetFolderPath('Desktop')
    if ([string]::IsNullOrWhiteSpace($desktop) -or -not (Test-Path -LiteralPath $desktop -PathType Container)) {
        throw "Desktop folder not found: $desktop"
    }

    $backupA = Join-Path $desktop 'GodOfWar-SaveBackup-2026-09-13_21-53-50'
    $backupB = Join-Path $desktop 'GodOfWar-SaveBackup-2026-09-13_22-01-52'
    $saveA = Resolve-FrozenGameSave $backupA
    $saveB = Resolve-FrozenGameSave $backupB

    $activeSaveDir = Join-Path $HOME 'Saved Games\God of War'
    $resolvedA = (Resolve-Path -LiteralPath $saveA).Path
    $resolvedB = (Resolve-Path -LiteralPath $saveB).Path
    if ($resolvedA.StartsWith($activeSaveDir, [System.StringComparison]::OrdinalIgnoreCase) -or
        $resolvedB.StartsWith($activeSaveDir, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Refusing to use the active God of War save tree.'
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($null -eq $python) { throw 'Python executable not found on PATH.' }

    $scanner = Join-Path $repo 'tools\v0.10.5\analyze-collectible-changed-stream-fingerprint.py'
    if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) {
        throw "Changed-stream fingerprint scanner missing: $scanner"
    }

    Write-Host "Frozen A: $saveA"
    Write-Host "Frozen B: $saveB"
    Write-Host 'The report emits hashes, offsets, sizes, ordinals, known checkpoint fields, and allowlisted engine identifiers only.'

    & $python.Source $scanner `
        --save-a $saveA `
        --save-b $saveB `
        --output-json $reportJson `
        --output-md $reportMd `
        --summary $summaryPath 2>&1 | Tee-Object -FilePath $pythonOutput
    $scanExit = $LASTEXITCODE
    if ($scanExit -ne 0) { throw "Changed-stream fingerprint scanner exited with code $scanExit" }

    if (-not (Test-Path -LiteralPath $reportJson -PathType Leaf)) {
        throw 'Fingerprint JSON report was not produced.'
    }
    $report = Get-Content -LiteralPath $reportJson -Raw | ConvertFrom-Json
    if ($report.runtime_generation_allowed -ne $false) {
        throw 'Fail-closed runtime gate missing from fingerprint report.'
    }
    if ($report.source_hashes_unchanged -ne $true) {
        throw 'Frozen backup hash-preservation proof missing.'
    }
    if ($report.safety.active_save_opened -ne $false -or
        $report.safety.game_written -ne $false -or
        $report.safety.save_or_progression_written -ne $false -or
        $report.safety.arbitrary_save_bytes_emitted -ne $false -or
        $report.safety.only_allowlisted_engine_tokens_emitted -ne $true) {
        throw 'Fingerprint report safety contract was not preserved.'
    }
    if ($report.status -notin @('CHANGED_STREAMS_FINGERPRINTED', 'NO_CHANGED_ZLIB_RUNS')) {
        throw "Unexpected fingerprint status: $($report.status)"
    }

    Write-Host "COLLECTIBLE_CHANGED_STREAM_FINGERPRINT_COMPLETED status=$($report.status) runs=$($report.changed_run_count) anchor_runs=$($report.previous_adjacency_anchor_run_count)"
    Publish-TraceLog 'SCAN_COMPLETED_FAIL_CLOSED'
}
catch {
    $message = $_.Exception.ToString()
    try { $message | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-TraceLog 'SCAN_FAILED' } catch {
        Write-Host 'The scan failed and its log could not be published. Only then copy console output manually.' -ForegroundColor Red
    }
    exit 1
}
finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}
