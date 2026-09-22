param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-ravens-release-candidate'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

if ((& git branch --show-current).Trim() -ne $ExpectedBranch) {
    throw "Need branch $ExpectedBranch."
}
if (@(& git status --porcelain --untracked-files=no).Count -gt 0) {
    throw 'Tracked tree must be clean before proof refresh.'
}

$startHead = (& git rev-parse HEAD).Trim()
if ([string]::IsNullOrWhiteSpace($startHead)) { throw 'Could not resolve starting HEAD.' }

$prepare = Join-Path $repo 'tools\v0.10.5\prepare-all-ravens-delivery-candidate.py'
$proofRelative = 'archive/all-ravens/all-ravens-release-candidate-offline.json'
$proofPath = Join-Path $repo ($proofRelative -replace '/', [IO.Path]::DirectorySeparatorChar)
$candidateRoot = Join-Path $repo 'build\v0.10.5-all-ravens-release-candidate\offline\candidate\game-root'
$mapRelative = 'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
$eventRelative = 'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua'
$mapPath = Join-Path $candidateRoot ($mapRelative -replace '/', [IO.Path]::DirectorySeparatorChar)
$eventPath = Join-Path $candidateRoot ($eventRelative -replace '/', [IO.Path]::DirectorySeparatorChar)

foreach ($required in @($prepare, $proofPath, $mapPath, $eventPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Need proof-refresh file: $required"
    }
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/raven-delivery-proof-refresh-$stamp"
$outDir = Join-Path $repo ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$console = Join-Path $outDir 'console-log.txt'
$resultFile = Join-Path $outDir 'result.txt'
$errorFile = Join-Path $outDir 'error.txt'
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$backupDir = Join-Path ([IO.Path]::GetTempPath()) (
    'completionist-raven-proof-refresh-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$proofBackup = Join-Path $backupDir 'proof.json'
$mapBackup = Join-Path $backupDir 'mapmenu.lua'
$eventBackup = Join-Path $backupDir 'precisionchallenge.lua'
Copy-Item -LiteralPath $proofPath -Destination $proofBackup
Copy-Item -LiteralPath $mapPath -Destination $mapBackup
Copy-Item -LiteralPath $eventPath -Destination $eventBackup

$proofBeforeSha = (Get-FileHash -LiteralPath $proofPath -Algorithm SHA256).Hash.ToLowerInvariant()
$mapBeforeSha = (Get-FileHash -LiteralPath $mapPath -Algorithm SHA256).Hash.ToLowerInvariant()
$eventBeforeSha = (Get-FileHash -LiteralPath $eventPath -Algorithm SHA256).Hash.ToLowerInvariant()

$transcript = $false
$successCommitCreated = $false
$successCommitSha = $null

function Stop-LocalTranscript {
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
}

function Invoke-PythonLogged([string[]]$Arguments) {
    $pythonExe = 'python.exe'
    $prefix = @()
    & py.exe -3.14 -c 'import sys' 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pythonExe = 'py.exe'
        $prefix = @('-3.14')
    }

    $lines = @(& $pythonExe @prefix @Arguments 2>&1)
    $exitCode = $LASTEXITCODE
    $lines | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) {
        throw "Python command failed exit=$exitCode args=$($Arguments -join ' ')"
    }
}

function Assert-OnlyExpectedStaged([bool]$IncludeProof) {
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect staged paths.' }

    foreach ($path in $staged) {
        $isEvidence = $path.Replace('\','/').StartsWith($relativeDir + '/')
        $isProof = $IncludeProof -and $path.Replace('\','/') -eq $proofRelative
        if (-not $isEvidence -and -not $isProof) {
            throw "Unexpected staged path: $path"
        }
    }

    if ($IncludeProof -and $proofRelative -notin @($staged | ForEach-Object { $_.Replace('\','/') })) {
        throw 'Refreshed proof was not staged.'
    }
}

function Commit-Evidence([string]$Message, [bool]$IncludeProof) {
    Stop-LocalTranscript

    if ($IncludeProof) {
        & git add -- $proofRelative
        if ($LASTEXITCODE -ne 0) { throw 'git add proof failed.' }
    }
    & git add -f -- $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'git add evidence failed.' }

    Assert-OnlyExpectedStaged $IncludeProof

    $commitPaths = @($relativeDir)
    if ($IncludeProof) { $commitPaths = @($proofRelative, $relativeDir) }
    & git commit -m $Message -- @commitPaths | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git commit evidence failed.' }

    return (& git rev-parse HEAD).Trim()
}

function Push-Commit([string]$CommitSha) {
    & git push origin "HEAD:$ExpectedBranch" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "git push failed for local commit $CommitSha"
    }
}

function Restore-PreRefreshState {
    Stop-LocalTranscript

    Copy-Item -LiteralPath $proofBackup -Destination $proofPath -Force
    Copy-Item -LiteralPath $mapBackup -Destination $mapPath -Force
    Copy-Item -LiteralPath $eventBackup -Destination $eventPath -Force

    & git reset --quiet HEAD -- $proofRelative $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'Could not clear staged proof/evidence after refresh failure.' }

    $proofAfter = (Get-FileHash -LiteralPath $proofPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $mapAfter = (Get-FileHash -LiteralPath $mapPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $eventAfter = (Get-FileHash -LiteralPath $eventPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($proofAfter -ne $proofBeforeSha -or
        $mapAfter -ne $mapBeforeSha -or
        $eventAfter -ne $eventBeforeSha) {
        throw 'Pre-refresh bytes were not restored exactly.'
    }

    $tracked = @(& git status --porcelain --untracked-files=no)
    if ($tracked.Count -ne 0) {
        Write-Host 'Tracked state after rollback:'
        $tracked | ForEach-Object { Write-Host $_ }
        throw 'Tracked tree/index did not return to pre-refresh clean state.'
    }
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true
    Write-Host 'RAVEN DELIVERY PROOF REFRESH - START'
    Write-Host "branch=$ExpectedBranch"
    Write-Host "start_head=$startHead"

    Invoke-PythonLogged @($prepare, '--refresh-proof')
    Invoke-PythonLogged @($prepare, '--check')

    $changed = @(& git diff --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect proof-refresh diff.' }
    if ($changed.Count -ne 1 -or $changed[0].Replace('\','/') -ne $proofRelative) {
        Write-Host 'Unexpected tracked changes:'
        $changed | ForEach-Object { Write-Host $_ }
        throw 'Proof refresh changed an unexpected tracked path.'
    }

    $proof = Get-Content -LiteralPath $proofPath -Raw | ConvertFrom-Json
    $mapEntry = $proof.files.PSObject.Properties[$mapRelative]
    $eventEntry = $proof.files.PSObject.Properties[$eventRelative]
    if ($null -eq $mapEntry) { throw 'Refreshed proof misses mapmenu.lua.' }
    if ($null -eq $eventEntry) { throw 'Refreshed proof misses precisionchallenge.lua.' }

    $mapSha = [string]$mapEntry.Value.sha256
    $mapBytes = [int64]$mapEntry.Value.bytes
    $eventSha = [string]$eventEntry.Value.sha256
    $eventBytes = [int64]$eventEntry.Value.bytes

    if ((Get-FileHash -LiteralPath $mapPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $mapSha) {
        throw 'Refreshed mapmenu.lua bytes do not match proof.'
    }
    if ((Get-FileHash -LiteralPath $eventPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $eventSha) {
        throw 'Refreshed precisionchallenge.lua bytes do not match proof.'
    }

    @(
        'result=RAVEN_DELIVERY_PROOF_REFRESH_PASSED'
        "timestamp=$(Get-Date -Format o)"
        "branch=$ExpectedBranch"
        "start_head=$startHead"
        "mapmenu_sha256=$mapSha"
        "mapmenu_bytes=$mapBytes"
        "precisionchallenge_sha256=$eventSha"
        "precisionchallenge_bytes=$eventBytes"
        'source_game_rebuild=false'
        'non_generated_binary_pins_unchanged=true'
        'transactional_candidate_refresh=true'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8

    Write-Host (
        "RAVEN_DELIVERY_PROOF_REFRESH_PASSED mapmenu_sha256=$mapSha " +
        "map_bytes=$mapBytes precisionchallenge_sha256=$eventSha event_bytes=$eventBytes")

    $successCommitSha = Commit-Evidence (
        'build(v0.10.5): refresh final Raven delivery proof') $true
    $successCommitCreated = $true
    Push-Commit $successCommitSha

    if (@(& git status --porcelain --untracked-files=no).Count -ne 0) {
        throw 'Tracked tree not clean after successful proof push.'
    }

    Write-Host "Evidence pushed: $relativeDir"
    Write-Host "RAVEN_DELIVERY_PROOF_REFRESH_COMMIT=$successCommitSha"
}
catch {
    $outer = $_
    Stop-LocalTranscript

    if ($successCommitCreated) {
        Write-Host (
            "RAVEN_DELIVERY_PROOF_REFRESH_PUSH_FAILED_LOCAL_COMMIT_PRESERVED " +
            "commit=$successCommitSha reason=$($outer.Exception.Message)")
        Write-Host 'Do not reset this branch. Retry the push or inspect the preserved commit.'
        exit 1
    }

    $rollbackOK = $false
    try {
        Restore-PreRefreshState
        $rollbackOK = $true
    }
    catch {
        Write-Host "RAVEN_DELIVERY_PROOF_REFRESH_ROLLBACK_FAILED: $($_.Exception.Message)"
    }

    try { $outer.Exception.ToString() | Set-Content -LiteralPath $errorFile -Encoding UTF8 } catch {}
    try {
        @(
            'result=RAVEN_DELIVERY_PROOF_REFRESH_FAILED'
            "timestamp=$(Get-Date -Format o)"
            "branch=$ExpectedBranch"
            "start_head=$startHead"
            "reason=$($outer.Exception.Message)"
            "pre_refresh_state_restored=$($rollbackOK.ToString().ToLowerInvariant())"
        ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
    } catch {}

    Write-Host "RAVEN_DELIVERY_PROOF_REFRESH_FAILED: $($outer.Exception.Message)"

    if ($rollbackOK) {
        try {
            $failureCommit = Commit-Evidence (
                "test(v0.10.5): archive Raven proof refresh failure $stamp") $false
            Push-Commit $failureCommit
            Write-Host "Failure evidence pushed: $relativeDir commit=$failureCommit"
        }
        catch {
            Write-Host "FAILURE_EVIDENCE_PUSH_FAILED: $($_.Exception.Message)"
        }
    }
    else {
        Write-Host 'Failure evidence not committed because pre-refresh state was not restored exactly.'
    }

    exit 1
}
finally {
    Stop-LocalTranscript
    Remove-Item -LiteralPath $backupDir -Recurse -Force -ErrorAction SilentlyContinue
}
