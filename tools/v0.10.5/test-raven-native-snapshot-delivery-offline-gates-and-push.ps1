param(
    [string]$GameRootFixture = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$ExpectedBranch = 'codex/all-ravens-release-candidate'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

if ((& git branch --show-current).Trim() -ne $ExpectedBranch) {
    throw "Need branch $ExpectedBranch."
}
if (@(& git status --porcelain --untracked-files=no).Count -gt 0) {
    throw 'Tracked tree/index must be clean before offline gates.'
}

$inner = Join-Path $repo 'tools\v0.10.5\test-raven-native-snapshot-delivery-offline-gates.ps1'
if (-not (Test-Path -LiteralPath $inner -PathType Leaf)) {
    throw "Need inner offline gate: $inner"
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/raven-native-snapshot-delivery-offline-$stamp"
$outDir = Join-Path $repo ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$console = Join-Path $outDir 'console-log.txt'
$innerConsole = Join-Path $outDir 'offline-gates-console-log.txt'
$resultFile = Join-Path $outDir 'result.txt'
$errorFile = Join-Path $outDir 'error.txt'
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$transcript = $false
$startHead = (& git rev-parse HEAD).Trim()

function Stop-LocalTranscript {
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
}

function Assert-OnlyEvidenceStaged {
    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect staged paths.' }
    foreach ($path in $staged) {
        if (-not $path.Replace('\','/').StartsWith($relativeDir + '/')) {
            throw "Unexpected staged path: $path"
        }
    }
}

function Publish-Evidence([string]$Message) {
    Stop-LocalTranscript

    & git add -f -- $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'git add offline-gate evidence failed.' }
    Assert-OnlyEvidenceStaged

    & git commit -m $Message -- $relativeDir | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git commit offline-gate evidence failed.' }
    $commitSha = (& git rev-parse HEAD).Trim()

    & git push origin "HEAD:$ExpectedBranch" | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "git push failed for offline-gate evidence commit $commitSha"
    }
    return $commitSha
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true

    Write-Host 'RAVEN NATIVE SNAPSHOT DELIVERY OFFLINE GATES + EVIDENCE PUSH - START'
    Write-Host "branch=$ExpectedBranch"
    Write-Host "head_before_pull=$startHead"

    & git pull --ff-only origin $ExpectedBranch | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git pull --ff-only failed.' }

    $testedHead = (& git rev-parse HEAD).Trim()
    Write-Host "tested_head=$testedHead"

    # Start-Transcript does not reliably capture output emitted by a nested
    # pwsh process. Tee the complete child stream into its own evidence file
    # while still mirroring it to the user's terminal.
    & pwsh -NoProfile -ExecutionPolicy Bypass -File $inner -GameRootFixture $GameRootFixture -ExpectedBranch $ExpectedBranch 2>&1 |
        Tee-Object -FilePath $innerConsole
    $innerExit = $LASTEXITCODE
    if ($innerExit -ne 0) {
        throw "Offline Raven gates failed with exit=$innerExit"
    }
    if (-not (Test-Path -LiteralPath $innerConsole -PathType Leaf) -or
        (Get-Item -LiteralPath $innerConsole).Length -eq 0) {
        throw 'Offline Raven gates produced no archived child console output.'
    }

    @(
        'result=RAVEN_NATIVE_SNAPSHOT_DELIVERY_OFFLINE_GATES_PASSED'
        "timestamp=$(Get-Date -Format o)"
        "branch=$ExpectedBranch"
        "tested_head=$testedHead"
        "inner_exit=$innerExit"
        'console_archived=true'
        'inner_console_archived=true'
        'evidence_push_requested=true'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8

    Write-Host 'RAVEN_NATIVE_SNAPSHOT_DELIVERY_OFFLINE_GATES_AND_PUSH_PASSED'
    $commitSha = Publish-Evidence "test(v0.10.5): archive Raven offline gates $stamp"
    Write-Host "Offline gate evidence pushed: $relativeDir"
    Write-Host "RAVEN_OFFLINE_GATES_EVIDENCE_COMMIT=$commitSha"
    exit 0
}
catch {
    $outer = $_
    try { $outer.Exception.ToString() | Set-Content -LiteralPath $errorFile -Encoding UTF8 } catch {}
    try {
        @(
            'result=RAVEN_NATIVE_SNAPSHOT_DELIVERY_OFFLINE_GATES_FAILED'
            "timestamp=$(Get-Date -Format o)"
            "branch=$ExpectedBranch"
            "start_head=$startHead"
            "current_head=$((& git rev-parse HEAD).Trim())"
            "reason=$($outer.Exception.Message)"
            'console_archived=true'
            'evidence_push_requested=true'
        ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
    } catch {}

    Write-Host "RAVEN_NATIVE_SNAPSHOT_DELIVERY_OFFLINE_GATES_AND_PUSH_FAILED: $($outer.Exception.Message)"
    try {
        $commitSha = Publish-Evidence "test(v0.10.5): archive failed Raven offline gates $stamp"
        Write-Host "Failure evidence pushed: $relativeDir"
        Write-Host "RAVEN_OFFLINE_GATES_FAILURE_EVIDENCE_COMMIT=$commitSha"
    }
    catch {
        Write-Host "OFFLINE_GATE_EVIDENCE_PUSH_FAILED: $($_.Exception.Message)"
    }
    exit 1
}
finally {
    Stop-LocalTranscript
}
