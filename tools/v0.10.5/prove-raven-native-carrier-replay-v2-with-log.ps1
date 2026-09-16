param(
    [string]$EvidenceRoot = (Join-Path $env:USERPROFILE "Documents\GodOfWar-RavenForcedManual-20260915-225302")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false

$ExpectedBranch = "codex/all-collectibles-production-research"
$RequiredAncestor = "e0768abcd5ae110f8210b3943a5cce6cf803588a"
$AliveSave = Join-Path $EvidenceRoot "alive\863677734\game.sav"
$DeadSave = Join-Path $EvidenceRoot "dead\863677734\game.sav"
$archiveDir = $null
$archiveRelative = $null
$transcriptStarted = $false
$analysisFinished = $false

function Assert-NativeSuccess {
    param([string]$Operation)
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE"
    }
}

function Invoke-PythonLogged {
    param(
        [string[]]$Arguments,
        [string]$LogPath
    )

    $python = Get-Command python -ErrorAction SilentlyContinue
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -eq $python -and $null -eq $py) {
        throw "Python was not found on PATH."
    }

    if ($null -ne $python) {
        $output = @(& python @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
        $runner = "python"
    }
    else {
        $output = @(& py -3 @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
        $runner = "py -3"
    }

    $text = @($output | ForEach-Object { $_.ToString() })
    $text | Set-Content -LiteralPath $LogPath -Encoding utf8
    foreach ($line in $text) {
        Write-Host $line
    }
    if ($exitCode -ne 0) {
        throw "$runner failed with exit code $exitCode; full output: $LogPath"
    }
}

$repoRoot = (& git rev-parse --show-toplevel).Trim()
Assert-NativeSuccess "git rev-parse --show-toplevel"
Set-Location $repoRoot

$branch = (& git branch --show-current).Trim()
Assert-NativeSuccess "git branch --show-current"
if ($branch -ne $ExpectedBranch) {
    throw "Wrong branch. Expected '$ExpectedBranch', got '$branch'."
}

& git merge-base --is-ancestor $RequiredAncestor HEAD
if ($LASTEXITCODE -ne 0) {
    throw "HEAD does not contain required failed-replay evidence commit $RequiredAncestor."
}

$dirty = @(& git status --porcelain)
Assert-NativeSuccess "git status --porcelain"
if ($dirty.Count -ne 0) {
    throw "Working tree is not clean."
}
if (-not (Test-Path -LiteralPath $AliveSave -PathType Leaf)) {
    throw "ALIVE save not found: $AliveSave"
}
if (-not (Test-Path -LiteralPath $DeadSave -PathType Leaf)) {
    throw "DEAD save not found: $DeadSave"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archiveRelative = "archive/field-logs/source-scans/raven-native-carrier-replay-v2-$timestamp"
$archiveDir = Join-Path $repoRoot $archiveRelative
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null

$transcriptPath = Join-Path $archiveDir "transcript.txt"
Start-Transcript -Path $transcriptPath -Force | Out-Null
$transcriptStarted = $true

try {
    Write-Host "Raven native carrier bidirectional replay v2"
    Write-Host "Branch: $branch"
    Write-Host "Archive: $archiveRelative"

    (& git rev-parse HEAD).Trim() |
        Set-Content -LiteralPath (Join-Path $archiveDir "repo-head-before.txt") -Encoding utf8
    Assert-NativeSuccess "git rev-parse HEAD"
    (& git status --short) |
        Set-Content -LiteralPath (Join-Path $archiveDir "git-status-before.txt") -Encoding utf8
    Assert-NativeSuccess "git status --short"

    $toolDir = Join-Path $repoRoot "tools\v0.10.5"
    $parser = Join-Path $toolDir "gow-custom-userdata-carrier.py"
    $scanner = Join-Path $toolDir "gow-custom-userdata-carrier-scan.py"
    $proof = Join-Path $toolDir "prove-raven-native-carrier-replay-v2.py"

    Write-Host "Running carrier parser self-test..."
    Invoke-PythonLogged -Arguments @($parser, "selftest") -LogPath (Join-Path $archiveDir "carrier-parser-selftest.txt")

    Write-Host "Running carrier scanner self-test..."
    Invoke-PythonLogged -Arguments @($scanner, "selftest") -LogPath (Join-Path $archiveDir "carrier-scanner-selftest.txt")

    Write-Host "Running corrected replay v2 self-test..."
    Invoke-PythonLogged -Arguments @($proof, "selftest") -LogPath (Join-Path $archiveDir "replay-v2-selftest.txt")

    Write-Host "Replaying frozen ALIVE <-> DEAD carriers..."
    Invoke-PythonLogged -Arguments @(
        $proof,
        "analyse",
        "--alive", $AliveSave,
        "--dead", $DeadSave,
        "--output-dir", $archiveDir
    ) -LogPath (Join-Path $archiveDir "replay-v2-python-output.txt")

    $summaryPath = Join-Path $archiveDir "summary.json"
    if (-not (Test-Path -LiteralPath $summaryPath -PathType Leaf)) {
        throw "Replay v2 completed without summary.json."
    }
    $summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
    if ($summary.verdict -ne "RAVEN_NATIVE_CARRIER_BIDIRECTIONAL_REPLAY_EXACT") {
        throw "Unexpected replay v2 verdict: $($summary.verdict)"
    }
    if (-not $summary.forward_exact -or -not $summary.reverse_exact) {
        throw "Replay v2 verdict was exact but one direction was not exact."
    }

    $analysisFinished = $true
    Write-Host "Bidirectional replay is byte-for-byte exact."
    Stop-Transcript | Out-Null
    $transcriptStarted = $false

    & git add -f -- $archiveRelative
    Assert-NativeSuccess "git add Raven replay v2 evidence"
    & git diff --cached --quiet -- $archiveRelative
    if ($LASTEXITCODE -eq 0) { throw "Replay v2 produced no staged evidence." }
    if ($LASTEXITCODE -ne 1) { throw "git diff --cached failed with exit code $LASTEXITCODE" }

    & git commit -m "research: prove exact Raven carrier replay v2"
    Assert-NativeSuccess "git commit Raven replay v2 evidence"
    & git push origin "HEAD:$ExpectedBranch"
    Assert-NativeSuccess "git push Raven replay v2 evidence"
    $pushedHead = (& git rev-parse HEAD).Trim()
    Assert-NativeSuccess "git rev-parse pushed HEAD"

    Write-Host ""
    Write-Host "PUSHED_COMMIT=$pushedHead"
    Write-Host "RAVEN_NATIVE_CARRIER_REPLAY_V2_PASSED_AND_PUSHED"
}
catch {
    $primaryError = $_
    try {
        if ($null -ne $archiveDir -and (Test-Path -LiteralPath $archiveDir)) {
            @(
                "Raven native carrier replay v2 failed.",
                "analysis_finished=$analysisFinished",
                "error=$($primaryError.Exception.Message)",
                "timestamp=$(Get-Date -Format o)"
            ) | Set-Content -LiteralPath (Join-Path $archiveDir "ERROR.txt") -Encoding utf8
        }
        if ($transcriptStarted) {
            Write-Host "ERROR: $($primaryError.Exception.Message)"
            Stop-Transcript | Out-Null
            $transcriptStarted = $false
        }
        if ($null -ne $archiveRelative -and $null -ne $archiveDir -and (Test-Path -LiteralPath $archiveDir)) {
            & git add -f -- $archiveRelative
            if ($LASTEXITCODE -eq 0) {
                & git diff --cached --quiet -- $archiveRelative
                if ($LASTEXITCODE -eq 1) {
                    & git commit -m "research: archive failed Raven carrier replay v2"
                }
                & git push origin "HEAD:$ExpectedBranch"
                if ($LASTEXITCODE -eq 0) {
                    $failureHead = (& git rev-parse HEAD).Trim()
                    Write-Host "FAILURE_EVIDENCE_PUSHED_COMMIT=$failureHead"
                    Write-Host "RAVEN_NATIVE_CARRIER_REPLAY_V2_FAILED_BUT_EVIDENCE_PUSHED"
                }
            }
        }
    }
    catch {
        Write-Host "Failure-evidence archival also failed: $($_.Exception.Message)"
    }
    throw $primaryError
}
