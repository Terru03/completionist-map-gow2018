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
$preflightJson = Join-Path $logDir 'preflight.json'
$resultPath = Join-Path $logDir 'result.txt'
$preexistingPath = Join-Path $logDir 'preexisting-unstaged-tracked.txt'
$scriptPath = Join-Path $repo 'tools\v0.10.5\capture-raven-scheduler-allocator-runtime.py'
$compatScriptPath = Join-Path $repo 'tools\v0.10.5\run-raven-scheduler-allocator-runtime-compat.py'
$exePath = Join-Path $GameRoot 'GoW.exe'
$wadPath = Join-Path $GameRoot 'exec\wad\pc_le\alf355_chiseldungeon.wad'
$expectedExeHash = 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452'
$expectedWadHash = '2e66a927426e83d4e7f2d6a17d5a3fd1387b1ddd415b7a5c43dc0d96fd7f5268'
$succeeded = $false
$failure = ''
$gameLaunched = $false
$published = $false
$transcriptStarted = $false
$launcherPid = $null
$gamePid = $null

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Get-ExactGameProcess {
    param([string]$ExpectedPath)

    $expectedFull = [System.IO.Path]::GetFullPath($ExpectedPath)
    $candidates = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessName -in @('GoW', 'GodOfWar')
    })
    foreach ($candidate in $candidates) {
        $candidatePath = $null
        try { $candidatePath = $candidate.Path } catch { }
        if ([string]::IsNullOrWhiteSpace($candidatePath)) {
            try { $candidatePath = $candidate.MainModule.FileName } catch { }
        }
        if ([string]::IsNullOrWhiteSpace($candidatePath)) { continue }
        try { $candidateFull = [System.IO.Path]::GetFullPath($candidatePath) } catch { continue }
        if ([string]::Equals($candidateFull, $expectedFull, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $candidate
        }
    }
    return $null
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

    foreach ($path in @($scriptPath, $compatScriptPath, $exePath, $wadPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
    }
    $exeHash = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $wadHash = (Get-FileHash -LiteralPath $wadPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($exeHash -ne $expectedExeHash) { throw "GoW.exe SHA mismatch: $exeHash" }
    if ($wadHash -ne $expectedWadHash) { throw "Target WAD SHA mismatch: $wadHash" }
    if ($null -ne (Get-ExactGameProcess -ExpectedPath $exePath)) {
        throw 'God of War already running. Close it, then rerun this command.'
    }

    Write-Host 'Run static capturer preflight before game launch.'
    & python $scriptPath preflight --exe $exePath --wad $wadPath --output $preflightJson 2>&1 |
        Tee-Object -LiteralPath $pythonLog | Out-Host
    $preflightExit = $LASTEXITCODE
    if ($preflightExit -ne 0) { throw "Runtime capturer preflight failed with exit code $preflightExit. Game not launched." }

    $loggerProbe = '__CAPTURE_LOGGER_PREFLIGHT_OK__'
    Add-Content -LiteralPath $pythonLog -Value $loggerProbe -Encoding UTF8
    $loggerTail = Get-Content -LiteralPath $pythonLog -Tail 1
    if ($loggerTail -ne $loggerProbe) { throw 'Capture logger preflight failed. Game not launched.' }

    $toolCommit = (& git rev-parse HEAD).Trim()
    Write-Host ''
    Write-Host 'Game will start WITHOUT debugger attachment first.' -ForegroundColor Cyan
    Write-Host 'Let God of War reach the main menu. Do not load the save yet.' -ForegroundColor Cyan
    Write-Host 'When the main menu is fully usable, return to this PowerShell window and press Enter.' -ForegroundColor Cyan

    $launcher = Start-Process -FilePath $exePath -WorkingDirectory $GameRoot -PassThru
    $launcherPid = $launcher.Id
    $gameLaunched = $true
    Write-Host "Initial launch PID: $launcherPid"

    $deadline = (Get-Date).AddMinutes(2)
    $live = $null
    do {
        Start-Sleep -Milliseconds 500
        $live = Get-ExactGameProcess -ExpectedPath $exePath
    } while ($null -eq $live -and (Get-Date) -lt $deadline)
    if ($null -eq $live) {
        $launcherState = if (Get-Process -Id $launcherPid -ErrorAction SilentlyContinue) { 'still-running' } else { 'exited-or-handed-off' }
        throw "No live GoW.exe matching '$exePath' appeared within two minutes. Initial PID $launcherPid is $launcherState."
    }

    $gamePid = $live.Id
    Write-Host "Initial live GoW process: PID $gamePid"
    if ($gamePid -ne $launcherPid) {
        Write-Host "Steam/process handoff detected: initial PID $launcherPid -> live GoW PID $gamePid"
    }

    # Do not attach during startup. Let Steam/GoW finish any early process
    # handoffs and anti-tamper/startup work first. The target Alfheim WAD should
    # not be loaded until the operator later loads the save, so this still
    # preserves the relevant target-registry lifecycle for the capture.
    [void](Read-Host 'At the fully loaded MAIN MENU, press Enter to attach debugger (do NOT load the save yet)')

    # Re-discover after the human wait because Steam/GoW can replace the process
    # during startup. Require the final exact-path process to remain alive for a
    # short stability window before debugger attachment.
    $stableDeadline = (Get-Date).AddMinutes(2)
    $stablePid = $null
    $stableSince = $null
    do {
        $candidate = Get-ExactGameProcess -ExpectedPath $exePath
        if ($null -eq $candidate) {
            $stablePid = $null
            $stableSince = $null
        }
        elseif ($stablePid -ne $candidate.Id) {
            $stablePid = $candidate.Id
            $stableSince = Get-Date
            Write-Host "Main-menu candidate GoW PID: $stablePid"
        }
        elseif ($null -ne $stableSince -and ((Get-Date) - $stableSince).TotalSeconds -ge 5) {
            break
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $stableDeadline)

    if ($null -eq $stablePid -or $null -eq $stableSince -or ((Get-Date) - $stableSince).TotalSeconds -lt 5) {
        throw 'Could not obtain a stable exact-path GoW.exe process for five seconds after main-menu confirmation.'
    }

    $gamePid = $stablePid
    Write-Host "Stable main-menu GoW process ready for debugger attach: PID $gamePid"
    Write-Host 'Attaching debugger now. Keep the game at the main menu until Debugger ready appears.' -ForegroundColor Cyan

    $savedErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & python $compatScriptPath capture --pid $gamePid --exe $exePath --wad $wadPath --tool-commit $toolCommit --output $captureJson --runs 2 2>&1 |
            ForEach-Object {
                $line = [string]$_
                Add-Content -LiteralPath $pythonLog -Value $line -Encoding UTF8
                Write-Host $line
            }
        $pythonExit = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $savedErrorActionPreference
    }
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
        "launcher_pid=$launcherPid"
        "game_pid=$gamePid"
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
        "launcher_pid=$launcherPid"
        "game_pid=$gamePid"
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
