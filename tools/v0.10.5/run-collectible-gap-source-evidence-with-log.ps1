param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/source-scans/collectible-gap-source-evidence-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$reportJson = Join-Path $logDir 'source-evidence.json'
$reportMd = Join-Path $logDir 'source-evidence.md'
$pythonOutput = Join-Path $logDir 'python-output.txt'
$published = $false
$transcriptStarted = $false

function Publish-Log([string]$Result) {
    if ($script:published) { return }
    $script:published = $true
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

    $allowed = @('console-log.txt','source-evidence.json','source-evidence.md','python-output.txt','result.txt','error.txt')
    $unexpected = @(Get-ChildItem -LiteralPath $logDir -File | Where-Object { $_.Name -notin $allowed })
    if ($unexpected.Count -gt 0) { throw "Unexpected log files: $($unexpected.Name -join ', ')" }

    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    $stagedNow = @(& git diff --cached --name-only)
    $prefix = ($relativeLogDir -replace '\\','/').TrimEnd('/') + '/'
    $foreign = @($stagedNow | Where-Object { -not (($_ -replace '\\','/').StartsWith($prefix)) })
    if ($foreign.Count -gt 0) {
        & git restore --staged -- $relativeLogDir 2>$null
        throw "Refusing unrelated staged paths: $($foreign -join ', ')"
    }

    & git diff --cached --quiet -- $relativeLogDir
    if ($LASTEXITCODE -eq 0) { return }
    & git commit -m "Archive collectible native gap source evidence $stamp" -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
    & git push origin "HEAD:$expectedBranch"
    if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true

    Write-Host '=== Completionist Map collectible native gap source evidence ==='
    Write-Host "Repository: $repo"
    Write-Host 'Read-only native WAD/DCB scan. No game launch and no save/progression access.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }

    $staged = @(& git diff --cached --name-only)
    if ($staged.Count -gt 0) { throw "Pre-existing staged changes: $($staged -join ', ')" }

    $gameProcess = @(Get-Process -Name 'GoW' -ErrorAction SilentlyContinue)
    if ($gameProcess.Count -gt 0) { throw 'God of War is running. Close it before the read-only scan.' }

    $python = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
    if ($null -eq $python) { throw 'Python executable not found.' }

    $scanner = Join-Path $repo 'tools\v0.10.5\analyze-collectible-gap-source-evidence.py'
    if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) { throw "Scanner missing: $scanner" }
    $gameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
    if (-not (Test-Path -LiteralPath $gameRoot -PathType Container)) { throw "Game root missing: $gameRoot" }

    & $python.Source $scanner `
        --game-root $gameRoot `
        --output-json $reportJson `
        --output-md $reportMd 2>&1 | Tee-Object -FilePath $pythonOutput
    if ($LASTEXITCODE -ne 0) { throw "Source-evidence scanner exited with code $LASTEXITCODE" }

    $report = Get-Content -LiteralPath $reportJson -Raw | ConvertFrom-Json
    if ($report.runtime_generation_allowed -ne $false) { throw 'Fail-closed runtime gate missing.' }
    if ($report.catalogue_mutated -ne $false) { throw 'Probe claims catalogue mutation.' }
    if ($report.safety.active_save_opened -ne $false -or
        $report.safety.game_written -ne $false -or
        $report.safety.save_or_progression_written -ne $false) {
        throw 'Safety contract was not preserved.'
    }

    Write-Host "COLLECTIBLE_GAP_SOURCE_EVIDENCE_COMPLETED shiphead_paths=$($report.raw_carrier_summary.shiphead_placement_paths) nornir_paths=$($report.raw_carrier_summary.nornir_placement_paths)"
    Publish-Log 'SCAN_COMPLETED_FAIL_CLOSED'
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "SCAN_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Log 'SCAN_FAILED' } catch {
        Write-Host 'The scan failed and its log could not be published; only then copy console output manually.' -ForegroundColor Red
    }
    exit 1
}
finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}
