param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $repo

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeLogDir = "archive/field-logs/runtime-captures/unloaded-checkpoint-oracle-$stamp"
$logDir = Join-Path $repo $relativeLogDir
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$consoleLog = Join-Path $logDir 'console-log.txt'
$targetRelative = 'mods\lua\gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
$targetPath = Join-Path $GameRoot $targetRelative
$templatePath = Join-Path $repo 'tools\v0.10.5\unloaded-checkpoint-oracle-probe.lua'
$builderPath = Join-Path $repo 'tools\v0.10.5\build-unloaded-checkpoint-oracle-probe.py'
$cataloguePath = Join-Path $repo 'catalogue\odins-ravens.json'
$loaderLogPath = Join-Path $GameRoot 'mods\loader_log.txt'
$exePath = Join-Path $GameRoot 'GoW.exe'
$tempBackup = Join-Path $env:TEMP ("completionist-checkpoint-oracle-$stamp.bak")
$tempProbe = Join-Path $env:TEMP ("completionist-checkpoint-oracle-$stamp.lua")
$targetRestored = $false
$transcriptStarted = $false
$gameLaunched = $false
$probeOutputFound = $false
$gatePassed = $false
$published = $false
$loaderBeforeLines = @()
$loaderBeforeHash = ''

function Stop-LocalTranscript {
    if ($script:transcriptStarted) {
        Stop-Transcript | Out-Null
        $script:transcriptStarted = $false
    }
}

function Restore-Target {
    if ($script:targetRestored) { return }
    if (Test-Path -LiteralPath $tempBackup -PathType Leaf) {
        [IO.File]::WriteAllBytes($targetPath, [IO.File]::ReadAllBytes($tempBackup))
        $script:targetRestored = $true
    }
}

function Wait-ForConfirmedGameExit {
    while ($true) {
        Read-Host 'After God of War has fully exited, press Enter to capture log and restore precisionchallenge.lua' | Out-Null
        $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') })
        if ($running.Count -eq 0) { return }
        Write-Host 'God of War is still running. Quit it fully first.' -ForegroundColor Yellow
    }
}

function Write-Result([string]$result) {
    @(
        "result=$result"
        "timestamp=$(Get-Date -Format o)"
        "branch=$expectedBranch"
        "game_launched=$($script:gameLaunched.ToString().ToLowerInvariant())"
        "target_restored=$($script:targetRestored.ToString().ToLowerInvariant())"
        "probe_output_found=$($script:probeOutputFound.ToString().ToLowerInvariant())"
        "unloaded_state_oracle_pass=$($script:gatePassed.ToString().ToLowerInvariant())"
        'probe_read_only=true'
        'probe_save_writes=false'
        'probe_progression_writes=false'
        'probe_streaming_writes=false'
        'helper_save_writes=false'
        'normal_game_save_activity_not_blocked=true'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'result.txt') -Encoding UTF8
}

function Publish-Capture([string]$result) {
    if ($script:published) { return }
    Stop-LocalTranscript
    Write-Result $result
    & git add -- $relativeLogDir
    if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
    & git diff --cached --quiet -- $relativeLogDir
    if ($LASTEXITCODE -eq 0) {
        $script:published = $true
        return
    }
    if ($LASTEXITCODE -ne 1) { throw 'Unable to inspect staged capture.' }
    & git commit -m "Archive unloaded checkpoint oracle probe $stamp" -- $relativeLogDir | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
    & git push origin "HEAD:$expectedBranch" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
    $script:published = $true
}

try {
    Start-Transcript -LiteralPath $consoleLog -Force | Out-Null
    $transcriptStarted = $true
    Write-Host '=== Completionist Map unloaded checkpoint oracle probe ==='
    Write-Host "Repository: $repo"
    Write-Host "Game root: $GameRoot"
    Write-Host 'Probe reads root __PickleTable.__subobjs, exact GameObject identity, loaded WAD list, and RegionSummary aggregates.'
    Write-Host 'It makes no save, progression, quest, marker, streaming, or object lifecycle calls.'

    $branch = (& git branch --show-current).Trim()
    if ($branch -ne $expectedBranch) { throw "Wrong branch. Expected '$expectedBranch', found '$branch'." }
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect staged changes.' }
    if ($staged.Count -gt 0) { throw "Refusing to run with staged changes: $($staged -join ', ')" }
    foreach ($path in @($targetPath, $templatePath, $builderPath, $cataloguePath, $exePath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
    }
    if (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }) {
        throw 'God of War is already running. Close it first.'
    }

    & python $builderPath --template $templatePath --catalogue $cataloguePath --output $tempProbe
    if ($LASTEXITCODE -ne 0) { throw 'Probe build failed.' }
    $originalBytes = [IO.File]::ReadAllBytes($targetPath)
    [IO.File]::WriteAllBytes($tempBackup, $originalBytes)
    $originalHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $probeHash = (Get-FileHash -LiteralPath $tempProbe -Algorithm SHA256).Hash.ToLowerInvariant()
    if ([Text.Encoding]::UTF8.GetString($originalBytes).Contains('BEGIN COMPLETIONIST UNLOADED CHECKPOINT ORACLE PROBE')) {
        throw 'precisionchallenge.lua already contains this probe.'
    }
    $probeText = [IO.File]::ReadAllText($tempProbe, [Text.Encoding]::UTF8)
    $appendBytes = [Text.Encoding]::UTF8.GetBytes("`r`n" + $probeText.Replace("`n", "`r`n"))
    $combined = New-Object byte[] ($originalBytes.Length + $appendBytes.Length)
    [Array]::Copy($originalBytes, 0, $combined, 0, $originalBytes.Length)
    [Array]::Copy($appendBytes, 0, $combined, $originalBytes.Length, $appendBytes.Length)
    [IO.File]::WriteAllBytes($targetPath, $combined)
    $installedHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant()
    @(
        "precisionchallenge_before_sha256=$originalHash"
        "precisionchallenge_probe_installed_sha256=$installedHash"
        "probe_lua_sha256=$probeHash"
        "target=$targetPath"
        'probe_read_only=true'
        'probe_save_writes=false'
        'probe_progression_writes=false'
        'probe_streaming_writes=false'
    ) | Set-Content -LiteralPath (Join-Path $logDir 'installed-file-hashes.txt') -Encoding UTF8

    if (Test-Path -LiteralPath $loaderLogPath -PathType Leaf) {
        $loaderBeforeLines = @(Get-Content -LiteralPath $loaderLogPath)
        $loaderBeforeHash = (Get-FileHash -LiteralPath $loaderLogPath -Algorithm SHA256).Hash.ToLowerInvariant()
    }

    Write-Host ''
    Write-Host 'Probe installed. Load existing almost-done save. Enter any area with a Raven script so one OnRestoreCheckpoint fires.' -ForegroundColor Cyan
    Write-Host 'Do not kill, collect, open, or activate anything. Then quit God of War fully.' -ForegroundColor Cyan
    Write-Host ''
    Start-Process -FilePath $exePath -WorkingDirectory $GameRoot | Out-Null
    $gameLaunched = $true
    Wait-ForConfirmedGameExit

    if (Test-Path -LiteralPath $loaderLogPath -PathType Leaf) {
        Copy-Item -LiteralPath $loaderLogPath -Destination (Join-Path $logDir 'loader_log.txt') -Force
        $loaderAfterLines = @(Get-Content -LiteralPath $loaderLogPath)
        $loaderAfterHash = (Get-FileHash -LiteralPath $loaderLogPath -Algorithm SHA256).Hash.ToLowerInvariant()
        $prefixMatches = $loaderBeforeLines.Count -le $loaderAfterLines.Count
        if ($prefixMatches) {
            for ($i = 0; $i -lt $loaderBeforeLines.Count; $i++) {
                if ($loaderBeforeLines[$i] -cne $loaderAfterLines[$i]) {
                    $prefixMatches = $false
                    break
                }
            }
        }
        $freshLines = $loaderAfterLines
        $logMode = 'overwritten'
        if ($prefixMatches -and $loaderBeforeLines.Count -gt 0) {
            $freshLines = @($loaderAfterLines | Select-Object -Skip $loaderBeforeLines.Count)
            $logMode = 'appended'
        }
        @(
            "before_sha256=$loaderBeforeHash"
            "after_sha256=$loaderAfterHash"
            "before_lines=$($loaderBeforeLines.Count)"
            "after_lines=$($loaderAfterLines.Count)"
            "fresh_lines=$($freshLines.Count)"
            "mode=$logMode"
            "changed=$($loaderAfterHash -ne $loaderBeforeHash)"
        ) | Set-Content -LiteralPath (Join-Path $logDir 'loader-log-freshness.txt') -Encoding UTF8
        $probeLines = @($freshLines | Select-String -SimpleMatch '[CompletionistCheckpointOracle]' | ForEach-Object { $_.Line })
        if ($probeLines.Count -gt 0) {
            $probeOutputFound = $true
            $probeLines | Set-Content -LiteralPath (Join-Path $logDir 'probe-extract.txt') -Encoding UTF8
        } else {
            'NO_COMPLETIONIST_CHECKPOINT_ORACLE_LINES_FOUND' | Set-Content -LiteralPath (Join-Path $logDir 'probe-extract.txt') -Encoding UTF8
        }
    } else {
        'LOADER_LOG_NOT_FOUND' | Set-Content -LiteralPath (Join-Path $logDir 'probe-extract.txt') -Encoding UTF8
    }

    Restore-Target
    $restoredHash = (Get-FileHash -LiteralPath $targetPath -Algorithm SHA256).Hash.ToLowerInvariant()
    @(
        "precisionchallenge_before_sha256=$originalHash"
        "precisionchallenge_after_restore_sha256=$restoredHash"
        "exact_restore=$($restoredHash -eq $originalHash)"
    ) | Set-Content -LiteralPath (Join-Path $logDir 'restore-verification.txt') -Encoding UTF8
    if ($restoredHash -ne $originalHash) { throw 'precisionchallenge.lua restore hash mismatch.' }

    $extract = Join-Path $logDir 'probe-extract.txt'
    $vfIds = @(
        'raven_642d0d164af0a5d4076e77933c549a5d',
        'raven_e32f7bab42fd7298890f6aa56a734562',
        'raven_c945cb53465b58decfcbd4a221cb5326'
    )
    $vfExpected = @('false', 'true', 'true')
    $validation = New-Object System.Collections.Generic.List[string]
    $vfPass = $true
    for ($i = 0; $i -lt $vfIds.Count; $i++) {
        $line = @(Select-String -LiteralPath $extract -SimpleMatch "EXACT_STATE catalogueId=$($vfIds[$i]) " | ForEach-Object { $_.Line } | Select-Object -First 1)
        $ok = $line.Count -eq 1 -and $line[0] -match "ravenKilled=$($vfExpected[$i])(?: |$)"
        $vfPass = $vfPass -and $ok
        $validation.Add("veithurgard[$i].catalogue_id=$($vfIds[$i]) expected=$($vfExpected[$i]) pass=$($ok.ToString().ToLowerInvariant())")
    }
    $vfRegion = @(Select-String -LiteralPath $extract -SimpleMatch 'REGION_CHECK parent=RegionSummary_VF_Raven_Parent exactSeen=3 exactKilled=2 aggregateProgress=2 aggregateGoal=3 agrees=true' | Select-Object -First 1)
    $vfAggregatePass = $vfRegion.Count -eq 1
    $validation.Add("veithurgard.aggregate_2_of_3_pass=$($vfAggregatePass.ToString().ToLowerInvariant())")

    $unloadedExact = @(Select-String -LiteralPath $extract -Pattern 'EXACT_STATE .* resident=false ')
    $unloadedParents = @($unloadedExact | ForEach-Object {
        if ($_.Line -match ' parent=([^ ]+) ') { $Matches[1] }
    } | Sort-Object -Unique)
    $secondRegion = $null
    foreach ($parent in $unloadedParents) {
        if ($parent -eq 'RegionSummary_VF_Raven_Parent') { continue }
        $candidate = @(Select-String -LiteralPath $extract -Pattern ("REGION_CHECK parent=" + [regex]::Escape($parent) + ' exactSeen=([1-9][0-9]*) exactKilled=([0-9]+) aggregateProgress=\2 aggregateGoal=\1 agrees=true') | Select-Object -First 1)
        if ($candidate.Count -eq 1) { $secondRegion = $parent; break }
    }
    $secondPass = $null -ne $secondRegion
    $validation.Add("second_region=$secondRegion pass=$($secondPass.ToString().ToLowerInvariant())")
    $unloadedPass = $unloadedExact.Count -gt 0
    $validation.Add("exact_unloaded_records=$($unloadedExact.Count) pass=$($unloadedPass.ToString().ToLowerInvariant())")
    $unknownSafe = @(Select-String -LiteralPath $extract -SimpleMatch 'gate=fail_closed_until_fixture_validation').Count -gt 0
    $validation.Add("unknown_fail_closed_pass=$($unknownSafe.ToString().ToLowerInvariant())")
    $gatePassed = $vfPass -and $vfAggregatePass -and $secondPass -and $unloadedPass -and $unknownSafe
    $gateLabel = if ($gatePassed) { 'PASS' } else { 'BLOCKED' }
    $validation.Add("UNLOADED_STATE_ORACLE=$gateLabel")
    $validation | Set-Content -LiteralPath (Join-Path $logDir 'acceptance-validation.txt') -Encoding UTF8

    $captureResult = if ($gatePassed) { 'UNLOADED_STATE_ORACLE_PASS' } else { 'UNLOADED_STATE_ORACLE_BLOCKED' }
    Publish-Capture $captureResult
    if ($gatePassed) {
        Write-Host 'UNLOADED_STATE_ORACLE_PASS_AND_PUSHED' -ForegroundColor Green
    } else {
        Write-Host 'UNLOADED_STATE_ORACLE_BLOCKED_AND_PUSHED' -ForegroundColor Yellow
    }
}
catch {
    try { $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $logDir 'error.txt') -Encoding UTF8 } catch {}
    Write-Host "UNLOADED_CHECKPOINT_ORACLE_PROBE_FAILED: $($_.Exception.Message)" -ForegroundColor Red
    try { Restore-Target } catch {}
    try { Publish-Capture 'UNLOADED_STATE_ORACLE_PROBE_FAILED' } catch { Write-Host "LOG_PUBLICATION_FAILED: $($_.Exception.Message)" -ForegroundColor Red }
    exit 1
}
finally {
    try { Restore-Target } catch {}
    foreach ($path in @($tempBackup, $tempProbe)) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force -ErrorAction SilentlyContinue }
    }
    Stop-LocalTranscript
}
