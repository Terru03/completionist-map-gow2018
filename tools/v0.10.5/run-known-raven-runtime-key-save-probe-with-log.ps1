param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/source-scans/known-raven-runtime-key-save-probe-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$reportJson = Join-Path $logDir 'runtime-key-report.json'
$reportText = Join-Path $logDir 'runtime-key-report.txt'
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

function Publish-Log([string]$Result) {
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

        $allowed = @('console-log.txt','runtime-key-report.json','runtime-key-report.txt','python-output.txt','result.txt','error.txt')
        $unexpected = @(Get-ChildItem -LiteralPath $logDir -File | Where-Object { $_.Name -notin $allowed })
        if ($unexpected.Count -gt 0) {
            throw "Refusing to publish unexpected files: $($unexpected.Name -join ', ')"
        }
        if (@(Get-ChildItem -LiteralPath $logDir -Recurse -File -Filter '*.sav').Count -gt 0) {
            throw 'Refusing to publish a copied save file.'
        }

        & git add -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
        $stagedNow = @(& git diff --cached --name-only)
        $prefix = ($relativeLogDir -replace '\\','/').TrimEnd('/') + '/'
        $foreign = @($stagedNow | Where-Object { -not (($_ -replace '\\','/').StartsWith($prefix)) })
        if ($foreign.Count -gt 0) {
            & git restore --staged -- $relativeLogDir 2>$null
            throw "Refusing to commit unrelated staged paths: $($foreign -join ', ')"
        }
        & git diff --cached --quiet -- $relativeLogDir
        if ($LASTEXITCODE -eq 0) { return }
        & git commit -m "Archive known Raven runtime-key save probe $stamp" -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        & git push origin "HEAD:$expectedBranch"
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    }
    catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
        throw
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map known Raven runtime-key save probe ==='
    Write-Host "Repository: $repo"
    Write-Host 'Read-only frozen-backup scan. Active saves are never opened.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) {
        throw "Wrong branch. Expected '$expectedBranch', found '$branch'."
    }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) {
        throw "Refusing to run with pre-existing staged changes: $($staged -join ', ')"
    }

    if (@(Get-Process -Name 'GoW' -ErrorAction SilentlyContinue).Count -gt 0) {
        throw 'God of War is running. Close it before the forensic scan.'
    }

    $desktop = [Environment]::GetFolderPath('Desktop')
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

    $scanner = Join-Path $repo 'tools\v0.10.5\probe-known-raven-runtime-keys.py'
    if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) { throw "Scanner missing: $scanner" }

    Write-Host "Frozen A: $saveA"
    Write-Host "Frozen B: $saveB"
    Write-Host 'Probing the runtime-proven Raven UID, region UID, stock backing UID, quest name and world position.'

    & $python.Source $scanner `
        --save-a $saveA `
        --save-b $saveB `
        --output-json $reportJson `
        --output-text $reportText 2>&1 | Tee-Object -FilePath $pythonOutput
    $scanExit = $LASTEXITCODE
    if ($scanExit -ne 0) { throw "Runtime-key scanner exited with code $scanExit" }

    if (-not (Test-Path -LiteralPath $reportText -PathType Leaf)) { throw 'Runtime-key report was not produced.' }
    $reportLines = @(Get-Content -LiteralPath $reportText | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne '' })
    if ($reportLines -notcontains 'runtime_generation_allowed=false') {
        throw 'Fail-closed runtime gate missing from report.'
    }
    if ($reportLines -notcontains 'status=EVIDENCE_ONLY') {
        throw 'Unexpected report status.'
    }

    Write-Host 'KNOWN_RAVEN_RUNTIME_KEY_SAVE_PROBE_COMPLETED_FAIL_CLOSED'
    Publish-Log 'SCAN_COMPLETED'
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Log 'SCAN_FAILED' } catch {
        Write-Host 'The scan failed and its log could not be published. Only then copy console output manually.' -ForegroundColor Red
    }
    exit 1
}
finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}
