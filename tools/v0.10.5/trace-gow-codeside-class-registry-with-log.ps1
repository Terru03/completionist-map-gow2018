param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

$exe = 'G:\SteamLibrary\steamapps\common\GodOfWar\GoW.exe'
$db = Join-Path $repo '.research-index\gow-caebcb027980.sqlite'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relative = "archive/field-logs/source-scans/gow-codeside-class-registry-$stamp"
$outDir = Join-Path $repo $relative
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$json = Join-Path $outDir 'gow-codeside-class-registry.json'
$text = Join-Path $outDir 'gow-codeside-class-registry.txt'
$pythonOutput = Join-Path $outDir 'python-output.txt'
$resultPath = Join-Path $outDir 'result.txt'
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
        'analysis=gow_codeside_class_registry'
        'analysis_mode=read-only'
        'scan_scope=exact-registry-globals-and-direct-static-provenance-only'
        'broad_heuristic_scan=false'
        'production_oracle_status=BLOCKED_EXACT_UNLOADED_STATE_ORACLE'
        'game_launched=false'
        'active_save_opened=false'
        'active_save_modified=false'
        'save_or_progression_written=false'
        'exe_written=false'
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8

    & git add -- $relative
    if ($LASTEXITCODE -ne 0) { throw 'git add archive failed.' }
    & git diff --cached --quiet -- $relative
    if ($LASTEXITCODE -eq 1) {
        & git commit -m "Archive GoW CodeSideLuaClass registry $stamp" -- $relative | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit archive failed.' }
        & git push origin "HEAD:$expectedBranch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    } elseif ($LASTEXITCODE -ne 0) {
        throw 'git diff archive check failed.'
    }
    $script:published = $true
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true
    Write-Host '=== Completionist Map CodeSideLuaClass registry ==='
    Write-Host 'Read-only exact-global trace. No game launch. No save access. No broad scan.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing staged changes: $($staged -join ', ')" }

    $scriptPath = Join-Path $repo 'tools\v0.10.5\trace-gow-codeside-class-registry.py'
    if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { throw "Tracer missing: $scriptPath" }
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw "GoW.exe missing: $exe" }
    if (-not (Test-Path -LiteralPath $db -PathType Leaf)) { throw "Research index missing: $db" }

    $pythonExe = (Get-Command python.exe -ErrorAction Stop).Source
    & $pythonExe -I -m py_compile $scriptPath 2>&1 | Tee-Object -FilePath $pythonOutput
    if ($LASTEXITCODE -ne 0) { throw 'Python syntax preflight failed.' }
    & $pythonExe -I $scriptPath --self-test 2>&1 | Tee-Object -FilePath $pythonOutput -Append
    if ($LASTEXITCODE -ne 0) { throw 'Tracer self-test failed.' }
    & $pythonExe -I $scriptPath --exe $exe --db $db --output-json $json --output-text $text 2>&1 |
        Tee-Object -FilePath $pythonOutput -Append
    if ($LASTEXITCODE -ne 0) { throw "Registry tracer exited $LASTEXITCODE." }

    $report = Get-Content -Raw -LiteralPath $json | ConvertFrom-Json
    if ($report.production_oracle_status -ne 'BLOCKED_EXACT_UNLOADED_STATE_ORACLE') {
        throw "Unexpected oracle status: $($report.production_oracle_status)"
    }
    if ($report.registry.static_count_after_crt_initializers -ne 2) {
        throw "Unexpected registry count: $($report.registry.static_count_after_crt_initializers)"
    }
    Publish 'ANALYSIS_PASSED'
    Write-Host 'GOW_CODESIDE_CLASS_REGISTRY_ARCHIVED_AND_PUSHED' -ForegroundColor Green
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
