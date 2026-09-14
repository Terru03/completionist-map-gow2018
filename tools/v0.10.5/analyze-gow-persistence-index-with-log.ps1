param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relative = "archive/field-logs/source-scans/gow-persistence-index-analysis-$stamp"
$outDir = Join-Path $repo $relative
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$json = Join-Path $outDir 'persistence-index-analysis.json'
$text = Join-Path $outDir 'persistence-index-analysis.txt'
$pythonOutput = Join-Path $outDir 'python-output.txt'
$db = Join-Path $repo '.research-index\gow-caebcb027980.sqlite'
$published = $false
$transcript = $false

function Publish([string]$Result) {
    if ($script:published) { return }
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
    @(
        "result=$Result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        "local_index=$db"
        'exe_rescanned=false'
        'active_save_opened=false'
        'game_written=false'
        'save_or_progression_written=false'
        'game_launched=false'
        'index_query_only=true'
    ) | Set-Content -LiteralPath (Join-Path $outDir 'result.txt') -Encoding UTF8

    & git add -- $relative
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relative
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "Archive GoW persistence index analysis $stamp" -- $relative | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
        & git push origin "HEAD:$expectedBranch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'git diff failed.'
    }
    $script:published = $true
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true
    Write-Host '=== Completionist Map persistence analysis from reusable index ==='
    Write-Host 'No GoW.exe rescan; this reads the existing local SQLite index only.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }
    if (-not (Test-Path -LiteralPath $db -PathType Leaf)) { throw "Research index missing: $db" }
    $scriptPath = Join-Path $repo 'tools\v0.10.5\analyze-gow-persistence-index.py'
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { throw 'Analysis script missing.' }

    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & python $scriptPath --db $db --output-json $json --output-text $text 2>&1 | Tee-Object -FilePath $pythonOutput
        $exit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldEap
    }
    if ($exit -ne 0) { throw "Analysis exited $exit. See $pythonOutput" }

    Publish 'ANALYSIS_PASSED'
    Write-Host 'GOW_PERSISTENCE_INDEX_ANALYSIS_PASSED_AND_PUSHED' -ForegroundColor Green
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "ANALYSIS_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish 'ANALYSIS_FAILED' } catch { Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    if ($transcript) { try { Stop-Transcript | Out-Null } catch {} }
}
