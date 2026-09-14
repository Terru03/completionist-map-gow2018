param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/source-scans/collectible-save-oracle-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$reportJson = Join-Path $logDir 'oracle-report.json'
$reportMd = Join-Path $logDir 'oracle-report.md'
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

function Publish-OracleLog([string]$Result) {
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
            'console-log.txt', 'oracle-report.json', 'oracle-report.md', 'summary.txt',
            'python-output.txt', 'result.txt', 'error.txt'
        )
        $unexpected = @(Get-ChildItem -LiteralPath $logDir -File | Where-Object { $_.Name -notin $allowed })
        if ($unexpected.Count -gt 0) {
            throw "Refusing to publish unexpected oracle-log files: $($unexpected.Name -join ', ')"
        }
        $saveCopies = @(Get-ChildItem -LiteralPath $logDir -Recurse -File -Filter '*.sav')
        if ($saveCopies.Count -gt 0) { throw 'Refusing to publish a copied save file.' }
        $oversized = @(Get-ChildItem -LiteralPath $logDir -File | Where-Object { $_.Length -gt 5MB })
        if ($oversized.Count -gt 0) {
            throw "Refusing to publish unexpectedly large oracle-log files: $($oversized.Name -join ', ')"
        }

        & git add -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git add of collectible oracle log directory failed.' }

        $stagedNow = @(& git diff --cached --name-only)
        if ($LASTEXITCODE -ne 0) { throw 'Unable to verify staged oracle files.' }
        $prefix = ($relativeLogDir -replace '\\','/').TrimEnd('/') + '/'
        $foreign = @($stagedNow | Where-Object { -not (($_ -replace '\\','/').StartsWith($prefix)) })
        if ($foreign.Count -gt 0) {
            & git restore --staged -- $relativeLogDir 2>$null
            throw "Refusing to commit unrelated staged paths: $($foreign -join ', ')"
        }

        & git diff --cached --quiet -- $relativeLogDir
        if ($LASTEXITCODE -eq 0) { return }
        & git commit -m "Archive collectible save-oracle probe $stamp" -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git commit of collectible oracle log directory failed.' }
        & git push origin "HEAD:$expectedBranch"
        if ($LASTEXITCODE -ne 0) { throw 'git push of collectible oracle log directory failed.' }
    }
    catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
        throw
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map exact collectible save-oracle probe ==='
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
    if ($gameProcess.Count -gt 0) { throw 'God of War is running. Close it before the read-only forensic scan.' }

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

    $scanner = Join-Path $repo 'tools\v0.10.5\probe-collectible-save-oracle.py'
    $catalogue = Join-Path $repo 'config\collectibles\v0.10.5\all-collectibles.json'
    if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) { throw "Oracle scanner missing: $scanner" }
    if (-not (Test-Path -LiteralPath $catalogue -PathType Leaf)) { throw "Collectible catalogue missing: $catalogue" }

    Write-Host "Frozen A: $saveA"
    Write-Host "Frozen B: $saveB"
    Write-Host 'The scanner emits hashes/offsets only; arbitrary save byte excerpts are not archived.'

    & $python.Source $scanner `
        --save-a $saveA `
        --save-b $saveB `
        --catalogue $catalogue `
        --output-json $reportJson `
        --output-md $reportMd `
        --summary $summaryPath 2>&1 | Tee-Object -FilePath $pythonOutput
    $scanExit = $LASTEXITCODE
    if ($scanExit -ne 0) { throw "Collectible save-oracle scanner exited with code $scanExit" }

    if (-not (Test-Path -LiteralPath $summaryPath -PathType Leaf)) { throw 'Oracle summary was not produced.' }
    $summary = Get-Content -LiteralPath $summaryPath -Raw
    if ($summary -notmatch '(?m)^status=BLOCKED_NO_PROVEN_ORACLE$') {
        throw 'Unexpected oracle status; this probe is not allowed to auto-open the runtime gate.'
    }
    if ($summary -notmatch '(?m)^runtime_generation_allowed=false$') {
        throw 'Fail-closed runtime gate missing from oracle summary.'
    }
    if ($summary -notmatch '(?m)^source_hashes_unchanged=true$') {
        throw 'Frozen backup hash-preservation proof missing.'
    }

    Write-Host 'COLLECTIBLE_SAVE_ORACLE_PROBE_COMPLETED_FAIL_CLOSED'
    Publish-OracleLog 'SCAN_COMPLETED_BLOCKED'
}
catch {
    $message = $_.Exception.ToString()
    try { $message | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-OracleLog 'SCAN_FAILED' } catch {
        Write-Host 'The scan failed and its log could not be published. Only then copy console output manually.' -ForegroundColor Red
    }
    exit 1
}
finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}
