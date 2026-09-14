param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/source-scans/collectible-gap-deep-evidence-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$reportJson = Join-Path $logDir 'deep-evidence.json'
$reportMd = Join-Path $logDir 'deep-evidence.md'
$pythonOutput = Join-Path $logDir 'python-output.txt'
$published = $false
$transcriptStarted = $false

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
            "read_only_native_asset_scan=true"
        ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8

        $allowed = @(
            'console-log.txt', 'deep-evidence.json', 'deep-evidence.md',
            'python-output.txt', 'result.txt', 'error.txt'
        )
        $unexpected = @(Get-ChildItem -LiteralPath $logDir -File | Where-Object { $_.Name -notin $allowed })
        if ($unexpected.Count -gt 0) {
            throw "Refusing to publish unexpected trace-log files: $($unexpected.Name -join ', ')"
        }
        $saveCopies = @(Get-ChildItem -LiteralPath $logDir -Recurse -File -Filter '*.sav')
        if ($saveCopies.Count -gt 0) { throw 'Refusing to publish a copied save file.' }
        $oversized = @(Get-ChildItem -LiteralPath $logDir -File | Where-Object { $_.Length -gt 8MB })
        if ($oversized.Count -gt 0) {
            throw "Refusing to publish unexpectedly large trace-log files: $($oversized.Name -join ', ')"
        }

        & git add -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git add of deep evidence log directory failed.' }

        $stagedNow = @(& git diff --cached --name-only)
        if ($LASTEXITCODE -ne 0) { throw 'Unable to verify staged trace files.' }
        $prefix = ($relativeLogDir -replace '\\','/').TrimEnd('/') + '/'
        $foreign = @($stagedNow | Where-Object { -not (($_ -replace '\\','/').StartsWith($prefix)) })
        if ($foreign.Count -gt 0) {
            & git restore --staged -- $relativeLogDir 2>$null
            throw "Refusing to commit unrelated staged paths: $($foreign -join ', ')"
        }

        & git diff --cached --quiet -- $relativeLogDir
        if ($LASTEXITCODE -eq 0) { return }
        & git commit -m "Archive collectible deep gap evidence $stamp" -- $relativeLogDir
        if ($LASTEXITCODE -ne 0) { throw 'git commit of deep evidence log directory failed.' }
        & git push origin "HEAD:$expectedBranch"
        if ($LASTEXITCODE -ne 0) { throw 'git push of deep evidence log directory failed.' }
    }
    catch {
        Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red
        throw
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map deep collectible gap native evidence ==='
    Write-Host "Repository: $repo"
    Write-Host 'Read-only native WAD scan. No game launch and no save/progression access.'

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
        throw 'God of War is running. Close it before the read-only native scan.'
    }

    $gameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
    if (-not (Test-Path -LiteralPath $gameRoot -PathType Container)) {
        throw "God of War root not found: $gameRoot"
    }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($null -eq $python) { throw 'Python executable not found on PATH.' }

    $scanner = Join-Path $repo 'tools\v0.10.5\analyze-collectible-gap-deep-evidence.py'
    if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) {
        throw "Deep evidence scanner missing: $scanner"
    }

    & $python.Source $scanner `
        --game-root $gameRoot `
        --output-json $reportJson `
        --output-md $reportMd 2>&1 | Tee-Object -FilePath $pythonOutput
    $scanExit = $LASTEXITCODE
    if ($scanExit -ne 0) { throw "Deep evidence scanner exited with code $scanExit" }

    if (-not (Test-Path -LiteralPath $reportJson -PathType Leaf)) {
        throw 'Deep evidence JSON report was not produced.'
    }
    $report = Get-Content -LiteralPath $reportJson -Raw | ConvertFrom-Json
    if ($report.runtime_generation_allowed -ne $false) {
        throw 'Fail-closed runtime gate missing from deep evidence report.'
    }
    if ($report.catalogue_mutated -ne $false) {
        throw 'Deep evidence probe unexpectedly claims catalogue mutation.'
    }
    if ($report.safety.active_save_opened -ne $false -or
        $report.safety.game_written -ne $false -or
        $report.safety.save_or_progression_written -ne $false) {
        throw 'Deep evidence report safety contract was not preserved.'
    }

    Write-Host "COLLECTIBLE_GAP_DEEP_EVIDENCE_COMPLETED distinct_physical=$($report.ship_head.distinct_physical_placements_from_carriers) ship03=$($report.ship_head.missing_number_reference_03.Count) ship05=$($report.ship_head.missing_number_reference_05.Count) cal500_hits=$($report.tyrs_vault_nornir.hits.Count)"
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
