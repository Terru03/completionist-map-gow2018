param(
    [string]$EvidenceRoot = (Join-Path $env:USERPROFILE "Documents\GodOfWar-RavenForcedManual-20260915-225302")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExpectedBranch = "codex/all-collectibles-production-research"
$RequiredAncestor = "73ee064b605c14a64034e56857d5c600665430a9"
$archiveDir = $null
$archiveRelative = $null
$transcriptStarted = $false
$analysisFinished = $false

$AliveSave = Join-Path $EvidenceRoot "alive\863677734\game.sav"
$DeadSave = Join-Path $EvidenceRoot "dead\863677734\game.sav"

function Assert-NativeSuccess {
    param([string]$Operation)
    if ($LASTEXITCODE -ne 0) {
        throw "$Operation failed with exit code $LASTEXITCODE"
    }
}

function Invoke-Python {
    param([string[]]$Arguments)

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $python) {
        & python @Arguments
        Assert-NativeSuccess "python"
        return
    }

    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $py) {
        & py -3 @Arguments
        Assert-NativeSuccess "py -3"
        return
    }

    throw "Python was not found on PATH."
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
    throw "HEAD does not contain required exact Raven resolution commit $RequiredAncestor."
}

$dirty = @(& git status --porcelain)
Assert-NativeSuccess "git status --porcelain"
if ($dirty.Count -ne 0) {
    throw "Working tree is not clean. This wrapper will not mix replay evidence with unrelated changes."
}

if (-not (Test-Path -LiteralPath $AliveSave -PathType Leaf)) {
    throw "ALIVE save not found: $AliveSave"
}
if (-not (Test-Path -LiteralPath $DeadSave -PathType Leaf)) {
    throw "DEAD save not found: $DeadSave"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$archiveRelative = "archive/field-logs/source-scans/raven-native-carrier-replay-$timestamp"
$archiveDir = Join-Path $repoRoot $archiveRelative
New-Item -ItemType Directory -Force -Path $archiveDir | Out-Null

$transcriptPath = Join-Path $archiveDir "transcript.txt"
Start-Transcript -Path $transcriptPath -Force | Out-Null
$transcriptStarted = $true

try {
    Write-Host "Raven native carrier structural replay"
    Write-Host "Branch: $branch"
    Write-Host "Archive: $archiveRelative"

    (& git rev-parse HEAD).Trim() |
        Set-Content -LiteralPath (Join-Path $archiveDir "repo-head-before.txt") -Encoding utf8
    Assert-NativeSuccess "git rev-parse HEAD"

    (& git status --short) |
        Set-Content -LiteralPath (Join-Path $archiveDir "git-status-before.txt") -Encoding utf8
    Assert-NativeSuccess "git status --short"

    $toolDir = Join-Path $repoRoot "tools\v0.10.5"
    $replay = Join-Path $toolDir "compare-raven-native-carriers.py"
    $carrierParser = Join-Path $toolDir "gow-custom-userdata-carrier.py"
    $carrierScanner = Join-Path $toolDir "gow-custom-userdata-carrier-scan.py"

    Write-Host "Running native carrier parser self-test..."
    Invoke-Python -Arguments @($carrierParser, "selftest")

    Write-Host "Running native carrier scanner self-test..."
    Invoke-Python -Arguments @($carrierScanner, "selftest")

    Write-Host "Running Raven structural replay self-test..."
    Invoke-Python -Arguments @($replay, "selftest")

    Write-Host "Replaying ALIVE -> DEAD and DEAD -> ALIVE structurally..."
    Invoke-Python -Arguments @(
        $replay,
        "analyse",
        "--alive", $AliveSave,
        "--dead", $DeadSave,
        "--output-dir", $archiveDir
    )

    $summaryPath = Join-Path $archiveDir "summary.json"
    if (-not (Test-Path -LiteralPath $summaryPath -PathType Leaf)) {
        throw "Replay completed without summary.json."
    }

    $summary = Get-Content -LiteralPath $summaryPath -Raw | ConvertFrom-Json
    if ($summary.verdict -ne "RAVEN_NATIVE_CARRIER_BIDIRECTIONAL_REPLAY_EXACT") {
        throw "Unexpected replay verdict: $($summary.verdict)"
    }

    $analysisFinished = $true
    Write-Host "Replay exact. Archiving and pushing evidence."

    Stop-Transcript | Out-Null
    $transcriptStarted = $false

    & git add -f -- $archiveRelative
    Assert-NativeSuccess "git add Raven replay evidence"

    & git diff --cached --quiet -- $archiveRelative
    if ($LASTEXITCODE -eq 0) {
        throw "Replay produced no staged evidence."
    }
    if ($LASTEXITCODE -ne 1) {
        throw "git diff --cached failed with exit code $LASTEXITCODE"
    }

    & git commit -m "research: prove Raven native carrier structural replay"
    Assert-NativeSuccess "git commit Raven replay evidence"

    & git push origin "HEAD:$ExpectedBranch"
    Assert-NativeSuccess "git push Raven replay evidence"

    $pushedHead = (& git rev-parse HEAD).Trim()
    Assert-NativeSuccess "git rev-parse pushed HEAD"

    Write-Host ""
    Write-Host "PUSHED_COMMIT=$pushedHead"
    Write-Host "RAVEN_NATIVE_CARRIER_REPLAY_PASSED_AND_PUSHED"
}
catch {
    $primaryError = $_
    try {
        if ($null -ne $archiveDir -and (Test-Path -LiteralPath $archiveDir)) {
            @(
                "Raven native carrier structural replay failed.",
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

        if ($null -ne $archiveRelative -and
            $null -ne $archiveDir -and
            (Test-Path -LiteralPath $archiveDir)) {
            & git add -f -- $archiveRelative
            if ($LASTEXITCODE -eq 0) {
                & git diff --cached --quiet -- $archiveRelative
                if ($LASTEXITCODE -eq 1) {
                    & git commit -m "research: archive failed Raven native carrier replay"
                }

                & git push origin "HEAD:$ExpectedBranch"
                if ($LASTEXITCODE -eq 0) {
                    $failureHead = (& git rev-parse HEAD).Trim()
                    Write-Host "FAILURE_EVIDENCE_PUSHED_COMMIT=$failureHead"
                    Write-Host "RAVEN_NATIVE_CARRIER_REPLAY_FAILED_BUT_EVIDENCE_PUSHED"
                }
                else {
                    Write-Host "RAVEN_NATIVE_CARRIER_REPLAY_FAILED_NOT_PUSHED"
                }
            }
        }
    }
    catch {
        Write-Host "Failure-evidence archival also failed: $($_.Exception.Message)"
        Write-Host "RAVEN_NATIVE_CARRIER_REPLAY_FAILED_NOT_PUSHED"
    }

    throw $primaryError
}
