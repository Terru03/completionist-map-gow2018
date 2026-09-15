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
$relativeLogDir = "archive/field-logs/runtime-captures/gow-raven-wad-context-diagnostic-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$pythonLog = Join-Path $logDir 'python-output.txt'
$resultPath = Join-Path $logDir 'result.txt'
$snapshotJson = Join-Path $logDir 'raven-context.json'
$scriptPath = Join-Path $repo 'tools\v0.10.5\capture-raven-wad-context-diagnostic.py'
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
        $message = if ($script:succeeded) { 'Archive Raven WAD context diagnostic' } else { 'Archive Raven WAD context diagnostic failure' }
        & git commit -m $message -- $relativeLogDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Capture commit failed.' }
        & git push origin "HEAD:$branch" | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Capture push failed.' }
    }
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true
    Write-Host '=== Canonical Raven WAD-context one-shot diagnostic ==='
    Write-Host 'NO debugger. NO breakpoints. NO process writes. NO thread suspension.'
    Write-Host 'Access is PROCESS_QUERY_INFORMATION + PROCESS_VM_READ only.'

    foreach ($path in @($scriptPath, $exePath, $wadPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
    }
    $exeHash = (Get-FileHash -LiteralPath $exePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $wadHash = (Get-FileHash -LiteralPath $wadPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($exeHash -ne $expectedExeHash) { throw "GoW.exe SHA mismatch: $exeHash" }
    if ($wadHash -ne $expectedWadHash) { throw "Target WAD SHA mismatch: $wadHash" }

    $live = Get-ExactGameProcess -ExpectedPath $exePath
    if ($null -eq $live) {
        Write-Host 'Launching GoW normally. No debugger will attach.' -ForegroundColor Cyan
        $launcher = Start-Process -FilePath $exePath -WorkingDirectory $GameRoot -PassThru
        $launcherPid = $launcher.Id
        Write-Host "Initial launch PID: $launcherPid"
        $deadline = (Get-Date).AddMinutes(2)
        do {
            Start-Sleep -Milliseconds 500
            $live = Get-ExactGameProcess -ExpectedPath $exePath
        } while ($null -eq $live -and (Get-Date) -lt $deadline)
        if ($null -eq $live) { throw 'No live exact-path GoW.exe appeared within two minutes.' }
    }
    else {
        Write-Host "Using already-running GoW PID $($live.Id)." -ForegroundColor Cyan
    }
    $gamePid = $live.Id

    Write-Host ''
    Write-Host 'Load the SAME Raven-alive save and stand near the exact alf355_chiseldungeon Raven. DO NOT kill/collect it.' -ForegroundColor Cyan
    [void](Read-Host 'When the Raven and area are fully loaded, press Enter for the ONE read-only snapshot')
    $process = Require-GameProcess
    Write-Host "Taking read-only diagnostic from PID $($process.Id)..." -ForegroundColor Cyan

    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & python $scriptPath --pid $process.Id --exe $exePath --wad $wadPath --output $snapshotJson 2>&1 |
            ForEach-Object {
                $line = [string]$_
                Add-Content -LiteralPath $pythonLog -Value $line -Encoding UTF8
                Write-Host $line
            }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $saved
    }
    if ($exitCode -ne 0) { throw "Read-only diagnostic failed with exit code $exitCode." }
    if (-not (Test-Path -LiteralPath $snapshotJson -PathType Leaf)) { throw 'Diagnostic produced no JSON.' }

    $report = Get-Content -LiteralPath $snapshotJson -Raw | ConvertFrom-Json
    $targetMatches = @($report.target_text_matches)
    $topCandidates = @($report.top_candidates)
    $registryIds = @()
    foreach ($item in $targetMatches) {
        if ($null -ne $item.context.registry_id) { $registryIds += [string]$item.context.registry_id }
    }
    $registryIds = @($registryIds | Sort-Object -Unique)

    @(
        'result=CAPTURED_READ_ONLY_WAD_CONTEXT_DIAGNOSTIC'
        "timestamp=$(Get-Date -Format o)"
        "branch=$branch"
        "launcher_pid=$launcherPid"
        "game_pid=$gamePid"
        "live_wad_context_count=$($report.live_wad_context_count)"
        "live_registry_ids=$(@($report.live_registry_ids) -join ',')"
        "target_text_match_count=$($report.target_text_match_count)"
        "target_registry_ids=$($registryIds -join ',')"
        "candidate_count=$($report.candidate_count)"
        $(if ($topCandidates.Count -gt 0) { 'top_candidate_tokens=' + (($topCandidates | ForEach-Object { $_.token_hex }) -join ',') } else { 'top_candidate_tokens=' })
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
    Write-Host 'WAD_CONTEXT_DIAGNOSTIC_COMPLETE' -ForegroundColor Green
    Write-Host "target_text_match_count=$($report.target_text_match_count)"
    Write-Host "target_registry_ids=$($registryIds -join ',')"
    Write-Host "candidate_count=$($report.candidate_count)"
}
catch {
    $failure = $_.Exception.ToString()
    $failure | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8
    @(
        'result=FAILED'
        "timestamp=$(Get-Date -Format o)"
        "branch=$branch"
        "launcher_pid=$launcherPid"
        "game_pid=$gamePid"
        'debugger_attached=false'
        'process_writes=false'
        'save_writes=false'
        'progression_writes=false'
        'gameobject_persistent_key_status=BLOCKED_EXACT_GAMEOBJECT_PERSISTENT_KEY'
        'production_oracle_status=BLOCKED_EXACT_UNLOADED_STATE_ORACLE'
        "failure=$($failure -replace "`r?`n", ' | ')"
    ) | Set-Content -LiteralPath $resultPath -Encoding UTF8
    Write-Host "WAD_CONTEXT_DIAGNOSTIC_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Publish-Capture } catch { Write-Host "CAPTURE_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    Stop-LocalTranscript
}
