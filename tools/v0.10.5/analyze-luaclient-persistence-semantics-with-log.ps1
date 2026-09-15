param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

$db = Join-Path $repo '.research-index\gow-caebcb027980.sqlite'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relative = "archive/field-logs/source-scans/luaclient-persistence-semantics-$stamp"
$outDir = Join-Path $repo $relative
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$json = Join-Path $outDir 'luaclient-persistence-semantics.json'
$text = Join-Path $outDir 'luaclient-persistence-semantics.txt'
$pythonOutput = Join-Path $outDir 'python-output.txt'
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
        'analysis=luaclient_persistence_semantics'
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
        & git commit -m "Archive LuaClient persistence semantics $stamp" -- $relative | Out-Host
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

    Write-Host '=== Completionist Map LuaClient persistence semantics ==='
    Write-Host 'SQLite-only analysis; no GoW.exe rescan; no game launch; no save I/O.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing staged changes: $($staged -join ', ')" }

    if (-not (Test-Path -LiteralPath $db -PathType Leaf)) { throw "Reusable index missing: $db" }
    $scriptPath = Join-Path $repo 'tools\v0.10.5\analyze-luaclient-persistence-semantics.py'
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { throw 'LuaClient analyzer missing.' }

    $pythonCmd = Get-Command python -ErrorAction Stop
    $pythonExe = $pythonCmd.Source
    Write-Host "PYTHON_EXE=$pythonExe"
    Write-Host "PYTHON_SCRIPT=$scriptPath"

    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $pythonExe -I -m py_compile $scriptPath 2>&1 | Tee-Object -FilePath $pythonOutput
        $compileExit = $LASTEXITCODE
        if ($compileExit -eq 0) {
            & $pythonExe -I $scriptPath --db $db --output-json $json --output-text $text 2>&1 | Tee-Object -FilePath $pythonOutput -Append
            $pythonExit = $LASTEXITCODE
        } else {
            $pythonExit = $compileExit
        }
    }
    finally {
        $ErrorActionPreference = $oldEap
    }
    if ($pythonExit -ne 0) { throw "LuaClient analyzer exited $pythonExit. Full output archived in $pythonOutput" }

    Publish 'ANALYSIS_PASSED'
    Write-Host 'LUACLIENT_PERSISTENCE_SEMANTICS_PASSED_AND_PUSHED' -ForegroundColor Green
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
