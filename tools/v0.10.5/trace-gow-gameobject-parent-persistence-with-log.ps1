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
$relative = "archive/field-logs/source-scans/gow-gameobject-parent-persistence-$stamp"
$outDir = Join-Path $repo $relative
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$console = Join-Path $outDir 'console-log.txt'
$json = Join-Path $outDir 'gow-gameobject-parent-persistence.json'
$text = Join-Path $outDir 'gow-gameobject-parent-persistence.txt'
$pythonOutput = Join-Path $outDir 'python-output.txt'
$resultPath = Join-Path $outDir 'result.txt'
$published = $false
$transcript = $false
$parentStatus = 'BLOCKED_EXACT_GAMEOBJECT_PARENT_DESCRIPTOR'
$callbackStatus = 'BLOCKED_EXACT_GAMEOBJECT_USERDATA_CALLBACK'
$keyStatus = 'BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY'
$oracleStatus = 'BLOCKED_EXACT_UNLOADED_STATE_ORACLE'

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
        'analysis=gow_gameobject_parent_persistence'
        'analysis_mode=read-only'
        "gameobject_parent_descriptor_status=$script:parentStatus"
        "gameobject_userdata_callback_status=$script:callbackStatus"
        "gameobject_persistent_key_status=$script:keyStatus"
        "production_oracle_status=$script:oracleStatus"
        'frozen_save_probe=false'
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
        & git commit -m "Archive GoW GameObject parent persistence $stamp" -- $relative | Out-Host
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
    Write-Host '=== Completionist Map GoW GameObject parent persistence ==='
    Write-Host 'Read-only exact parent/slot trace. No game launch or save access.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch: $branch" }
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing staged changes: $($staged -join ', ')" }

    $scriptPath = Join-Path $repo 'tools\v0.10.5\trace-gow-gameobject-parent-persistence.py'
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
    if ($LASTEXITCODE -ne 0) { throw "Parent-persistence tracer exited $LASTEXITCODE." }

    $report = Get-Content -Raw -LiteralPath $json | ConvertFrom-Json
    if ($report.gameobject_parent_descriptor_status -ne 'PASS_EXACT_GAMEOBJECT_PARENT_DESCRIPTOR') {
        throw "Unexpected parent descriptor status: $($report.gameobject_parent_descriptor_status)"
    }
    if ($report.gameobject_userdata_callback_status -notin @('PASS_EXACT_GAMEOBJECT_USERDATA_CALLBACK','BLOCKED_EXACT_GAMEOBJECT_USERDATA_CALLBACK')) {
        throw "Unexpected callback status: $($report.gameobject_userdata_callback_status)"
    }
    if ($report.gameobject_persistent_key_status -ne 'BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY') {
        throw "Unexpected persistent-key status: $($report.gameobject_persistent_key_status)"
    }
    if ($report.production_oracle_status -ne 'BLOCKED_EXACT_UNLOADED_STATE_ORACLE') {
        throw "Unexpected oracle status: $($report.production_oracle_status)"
    }
    if ($report.safety.frozen_save_opened -ne $false -or $report.safety.active_save_opened -ne $false) {
        throw 'Save safety flag changed.'
    }

    $script:parentStatus = $report.gameobject_parent_descriptor_status
    $script:callbackStatus = $report.gameobject_userdata_callback_status
    $script:keyStatus = $report.gameobject_persistent_key_status
    $script:oracleStatus = $report.production_oracle_status
    Publish 'ANALYSIS_PASSED'
    Write-Host 'GOW_GAMEOBJECT_PARENT_PERSISTENCE_ARCHIVED_AND_PUSHED' -ForegroundColor Green
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
