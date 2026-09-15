param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$branch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Run from inside completionist-map-gow2018 repository.' }
Set-Location $repo

$current = (& git branch --show-current).Trim()
if ($current -ne $branch) { throw "Wrong branch. Expected '$branch', found '$current'." }
if (@(& git diff --cached --name-only).Count -gt 0) { throw 'Pre-existing staged changes exist; capture refused.' }

& git pull --ff-only origin $branch | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Branch pull failed.' }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/runtime-captures/gow-raven-scheduler-allocator-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$pythonLog = Join-Path $logDir 'python-output.txt'
$captureJson = Join-Path $logDir 'capture.json'
$resultPath = Join-Path $logDir 'result.txt'
$preexistingPath = Join-Path $logDir 'preexisting-unstaged-tracked.txt'
$scriptPath = Join-Path $repo 'tools\v0.10.5\capture-raven-scheduler-allocator-runtime.py'
$exePath = Join-Path $GameRoot 'GoW.exe'
$wadPath = Join-Path $GameRoot 'exec\wad\pc_le\alf355_chiseldungeon.wad'
$expectedExeHash = 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452'
$expectedWadHash = '2e66a927426e83d4e7f2d6a17d5a3fd1387b1ddd415b7a5c43dc0d96fd7f5268'
$succeeded = $false
$failure = ''
$gameLaunched = $false
$published = $false
$transcriptStarted = $false

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Publish-Capture {
    if ($script:published) { return }
    $script:published = $true
    Stop-LocalTranscript
    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage capture directory.' }
    $staged = @(& git diff --cached --name-only --)
    foreach ($path in $staged) {
        if ($path -notlike "$relativeLogDir/*") { throw "Unexpected staged path outside capture: $path" }
    }
    if ($staged.Count -gt 0) {
        $message = if ($script:succeeded) {
            'Archive Raven scheduler allocator runtime capture'
        } else {
            'Archive Raven scheduler allocator runtime capture failure'
        }
        & git commit -m $message -- $relativeLogDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Capture commit failed.' }
        & git push origin "HEAD:$branch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Capture push failed.' }
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true
    Write-Host '=== Exact Raven scheduler/allocator two-reload capture ==='
    Write-Host 'Target: 95b9c644-4d47-9ac6-8207-b1829d02909b / alf355_chiseldungeon.wad / 0x32E3C60 / record 9633'
    Write-Host 'Tool writes no save, progression, collectible, or map-marker state.'
    Write-Host 'Tool temporarily changes three bytes in live process only. It restores each byte immediately and restores all before detach.'

    @(& git diff --name-status --ignore-submodules --) |
        Set-Content -LiteralPath $preexistingPath -Encoding UTF8

    foreach ($path in @($scriptPath, $exePath, $wadPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
    }
    $exeHash = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $wadHash = (Get-FileHash -LiteralPath $wadPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($exeHash -ne $expectedExeHash) { throw "GoW.exe SHA mismatch: $exeHash" }
    if ($wadHash -ne $expectedWadHash) { throw "Target WAD SHA mismatch: $wadHash" }
    if (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }) {
        throw 'God of War already running. Close it, then rerun this command.'
    }

    $toolCommit = (& git rev-parse HEAD).Trim()
    Write-Host ''
    Write-Host 'Game will start. Wait for debugger-ready line before loading save.' -ForegroundColor Cyan
    Write-Host 'Run A: load target save/context, reach alf355_chiseldungeon Raven, approach it, do not kill or collect.' -ForegroundColor Cyan
    Write-Host 'After RUN_A_EXACT_TARGET_CAPTURED: return to main menu, reload same save/context, approach same Raven again.' -ForegroundColor Cyan
    Write-Host 'If no capture line appears within 60 seconds at Raven, quit game. Wrapper will archive and push failure evidence.' -ForegroundColor Cyan
    Write-Host 'Do not inspect memory or logs. Wrapper collects and compares all data.' -ForegroundColor Cyan

    $game = Start-Process -FilePath $exePath -WorkingDirectory $GameRoot -PassThru
    $gameLaunched = $true
    $deadline = (Get-Date).AddMinutes(2)
    do {
        Start-Sleep -Milliseconds 500
        $live = Get-Process -Id $game.Id -ErrorAction SilentlyContinue
    } while ($null -eq $live -and (Get-Date) -lt $deadline)
    if ($null -eq $live) { throw 'GoW.exe process did not remain available for debugger attach.' }

    # Merge native stdout/stderr into one live stream so constructor/startup
    # tracebacks are preserved in the archive instead of collapsing to only
    # an exit code. Tee-Object keeps interactive capture prompts visible.
    & python $scriptPath capture --pid $game.Id --exe $exePath --wad $wadPath --tool-commit $toolCommit --output $captureJson --runs 2 2>&1 |
        Tee-Object -LiteralPath $pythonLog | Out-Host
    $pythonExit = $LASTEXITCODE
    Write-Host "python_exit_code=$pythonExit"
    if ($pythonExit -ne 0) { throw "Runtime capturer failed with exit code $pythonExit." }

    $capture = Get-Content -LiteralPath $captureJson -Raw | ConvertFrom-Json
    if ($capture.capture_complete -ne $true -or $capture.captured_runs -ne 2) {
        throw 'Two-run capture JSON is incomplete.'
    }
    $status = [string]$capture.gameobject_persistent_key_status
    @(
        "result=CAPTURED"
        "timestamp=$(Get-Date -Format o)"
        "branch=$branch"
        "tool_commit=$toolCommit"
        "game_launched=$($gameLaunched.ToString().ToLowerInvariant())"
        "captured_runs=$($capture.captured_runs)"
        "gameobject_persistent_key_status=$status"
        'production_oracle_status=BLOCKED_EXACT_UNLOADED_STATE_ORACLE'
        'save_writes=false'
        'progression_writes=false'
        'exe_disk_writes=false'
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8
    $succeeded = $true
    Publish-Capture
    Write-Host "$status"
    Write-Host 'BLOCKED_EXACT_UNLOADED_STATE_ORACLE'
    Write-Host "Capture archived and pushed: $relativeLogDir"
}
catch {
    $failure = $_.Exception.ToString()
    $failure | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8
    @(
        "result=FAILED"
        "timestamp=$(Get-Date -Format o)"
        "branch=$branch"
        "game_launched=$($gameLaunched.ToString().ToLowerInvariant())"
        'gameobject_persistent_key_status=BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY'
        'production_oracle_status=BLOCKED_EXACT_UNLOADED_STATE_ORACLE'
        'save_writes=false'
        'progression_writes=false'
        'exe_disk_writes=false'
        "failure=$($failure -replace "`r?`n", ' | ')"
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-Host "RUNTIME_CAPTURE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Capture } catch { Write-Host "CAPTURE_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    Stop-LocalTranscript
}
