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
$relativeLogDir = "archive/field-logs/runtime-captures/gow-raven-readonly-registry-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$resultPath = Join-Path $logDir 'result.txt'
$baselineJson = Join-Path $logDir 'baseline-main-menu.json'
$runAJson = Join-Path $logDir 'run-a-raven.json'
$betweenJson = Join-Path $logDir 'between-main-menu.json'
$runBJson = Join-Path $logDir 'run-b-raven.json'
$scriptPath = Join-Path $repo 'tools\v0.10.5\capture-raven-readonly-registry.py'
$exePath = Join-Path $GameRoot 'GoW.exe'
$wadPath = Join-Path $GameRoot 'exec\wad\pc_le\alf355_chiseldungeon.wad'
$expectedExeHash = 'caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452'
$expectedWadHash = '2e66a927426e83d4e7f2d6a17d5a3fd1387b1ddd415b7a5c43dc0d96fd7f5268'
$published = $false
$transcriptStarted = $false
$succeeded = $false
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
    foreach ($candidate in @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') })) {
        $candidatePath = $null
        try { $candidatePath = $candidate.Path } catch { }
        if ([string]::IsNullOrWhiteSpace($candidatePath)) {
            try { $candidatePath = $candidate.MainModule.FileName } catch { }
        }
        if ([string]::IsNullOrWhiteSpace($candidatePath)) { continue }
        try { $candidateFull = [System.IO.Path]::GetFullPath($candidatePath) } catch { continue }
        if ([string]::Equals($candidateFull, $expectedFull, [System.StringComparison]::OrdinalIgnoreCase)) { return $candidate }
    }
    return $null
}

function Require-GameProcess {
    $process = Get-ExactGameProcess -ExpectedPath $exePath
    if ($null -eq $process) { throw 'No live exact-path GoW.exe process found.' }
    $script:gamePid = $process.Id
    return $process
}

function Take-Snapshot {
    param([string]$Label, [string]$Output)
    $process = Require-GameProcess
    Write-Host "Taking read-only snapshot '$Label' from PID $($process.Id)..." -ForegroundColor Cyan
    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & python $scriptPath --pid $process.Id --exe $exePath --wad $wadPath --output $Output 2>&1 |
            ForEach-Object { Write-Host ([string]$_) }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $saved
    }
    if ($exitCode -ne 0) { throw "Read-only snapshot '$Label' failed with exit code $exitCode." }
    if (-not (Test-Path -LiteralPath $Output -PathType Leaf)) { throw "Snapshot '$Label' produced no JSON." }
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
        $message = if ($script:succeeded) { 'Archive read-only Raven registry capture' } else { 'Archive read-only Raven registry capture failure' }
        & git commit -m $message -- $relativeLogDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Capture commit failed.' }
        & git push origin "HEAD:$branch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Capture push failed.' }
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true
    Write-Host '=== Canonical Raven READ-ONLY registry capture ==='
    Write-Host 'NO debugger. NO breakpoints. NO process writes. NO thread suspension.'
    Write-Host 'Access is PROCESS_QUERY_INFORMATION + PROCESS_VM_READ only.'
    Write-Host 'Target: 95b9c644-4d47-9ac6-8207-b1829d02909b / alf355_chiseldungeon.wad / record 9633'

    foreach ($path in @($scriptPath, $exePath, $wadPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
    }
    $exeHash = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $wadHash = (Get-FileHash -LiteralPath $wadPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($exeHash -ne $expectedExeHash) { throw "GoW.exe SHA mismatch: $exeHash" }
    if ($wadHash -ne $expectedWadHash) { throw "Target WAD SHA mismatch: $wadHash" }
    if ($null -ne (Get-ExactGameProcess -ExpectedPath $exePath)) { throw 'God of War already running. Close it, then rerun this wrapper.' }

    Write-Host 'Launching GoW normally. No debugger will attach.' -ForegroundColor Cyan
    $launcher = Start-Process -FilePath $exePath -WorkingDirectory $GameRoot -PassThru
    $launcherPid = $launcher.Id
    Write-Host "Initial launch PID: $launcherPid"

    $deadline = (Get-Date).AddMinutes(2)
    $live = $null
    do {
        Start-Sleep -Milliseconds 500
        $live = Get-ExactGameProcess -ExpectedPath $exePath
    } while ($null -eq $live -and (Get-Date) -lt $deadline)
    if ($null -eq $live) { throw 'No live exact-path GoW.exe appeared within two minutes.' }
    $gamePid = $live.Id
    Write-Host "Live GoW PID: $gamePid"
    if ($gamePid -ne $launcherPid) { Write-Host "Steam/process handoff: $launcherPid -> $gamePid" }

    [void](Read-Host 'At the fully loaded MAIN MENU, press Enter for the baseline read-only snapshot')
    Take-Snapshot -Label 'baseline-main-menu' -Output $baselineJson

    Write-Host ''
    Write-Host 'RUN A: load the target save, go to the exact alf355_chiseldungeon Raven, approach it, DO NOT kill/collect it.' -ForegroundColor Cyan
    [void](Read-Host 'When standing near the live Raven and the area is fully loaded, press Enter for Run A snapshot')
    Take-Snapshot -Label 'run-a-raven' -Output $runAJson

    Write-Host ''
    Write-Host 'Return to the MAIN MENU and let it finish unloading the save.' -ForegroundColor Cyan
    [void](Read-Host 'At the fully loaded MAIN MENU again, press Enter for the between-runs snapshot')
    Take-Snapshot -Label 'between-main-menu' -Output $betweenJson

    Write-Host ''
    Write-Host 'RUN B: reload the SAME save, return to the SAME Raven, and again DO NOT kill/collect it.' -ForegroundColor Cyan
    [void](Read-Host 'When standing near the same live Raven and the area is fully loaded, press Enter for Run B snapshot')
    Take-Snapshot -Label 'run-b-raven' -Output $runBJson

    $a = Get-Content -LiteralPath $runAJson -Raw | ConvertFrom-Json
    $b = Get-Content -LiteralPath $runBJson -Raw | ConvertFrom-Json
    $aTop = @($a.top_candidates)
    $bTop = @($b.top_candidates)
    $sameTokens = @()
    foreach ($ca in $aTop) {
        foreach ($cb in $bTop) {
            if ([string]$ca.token_hex -eq [string]$cb.token_hex) {
                $sameTokens += [pscustomobject]@{ token = [string]$ca.token_hex; score_a = $ca.score; score_b = $cb.score; evidence_a = ($ca.evidence -join ','); evidence_b = ($cb.evidence -join ',') }
            }
        }
    }
    $sameTokens = @($sameTokens | Sort-Object token -Unique)

    @(
        'result=CAPTURED_READ_ONLY'
        "timestamp=$(Get-Date -Format o)"
        "branch=$branch"
        "launcher_pid=$launcherPid"
        "last_game_pid=$gamePid"
        "run_a_target_wad_outer_count=$($a.target_wad_outer_count)"
        "run_b_target_wad_outer_count=$($b.target_wad_outer_count)"
        "run_a_candidate_count=$($a.candidate_count)"
        "run_b_candidate_count=$($b.candidate_count)"
        "same_top_candidate_token_count=$($sameTokens.Count)"
        $(if ($sameTokens.Count -gt 0) { 'same_top_candidate_tokens=' + (($sameTokens | ForEach-Object { $_.token }) -join ',') } else { 'same_top_candidate_tokens=' })
        'debugger_attached=false'
        'breakpoints_installed=false'
        'process_writes=false'
        'thread_suspend_resume=false'
        'save_writes=false'
        'progression_writes=false'
        'gameobject_persistent_key_status=BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY'
        'production_oracle_status=BLOCKED_EXACT_UNLOADED_STATE_ORACLE'
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8

    $succeeded = $true
    Publish-Capture
    Write-Host 'READ_ONLY_TWO_RELOAD_CAPTURE_COMPLETE' -ForegroundColor Green
    Write-Host "same_top_candidate_token_count=$($sameTokens.Count)"
    foreach ($item in $sameTokens | Select-Object -First 10) {
        Write-Host "same_token=$($item.token) scoreA=$($item.score_a) scoreB=$($item.score_b)"
    }
    Write-Host 'BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY'
    Write-Host 'BLOCKED_EXACT_UNLOADED_STATE_ORACLE'
}
catch {
    $failure = $_.Exception.ToString()
    $failure | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8
    @(
        'result=FAILED'
        "timestamp=$(Get-Date -Format o)"
        "branch=$branch"
        "launcher_pid=$launcherPid"
        "last_game_pid=$gamePid"
        'debugger_attached=false'
        'process_writes=false'
        'save_writes=false'
        'progression_writes=false'
        'gameobject_persistent_key_status=BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY'
        'production_oracle_status=BLOCKED_EXACT_UNLOADED_STATE_ORACLE'
        "failure=$($failure -replace "`r?`n", ' | ')"
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-Host "READ_ONLY_CAPTURE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Capture } catch { Write-Host "CAPTURE_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    Stop-LocalTranscript
}
