param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [ValidateRange(30, 180)][int]$StartupTimeoutSeconds = 90,
    [ValidateRange(20, 90)][int]$MainMenuSettleSeconds = 40
)

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
    throw 'Tracked tree must be clean before live proof.'
}

$inner = Join-Path $repo 'tools\v0.10.5\run-raven-native-snapshot-delivery-live-proof-and-push.ps1'
if (-not (Test-Path -LiteralPath $inner -PathType Leaf)) {
    throw "Need inner live-proof runner: $inner"
}

$headBefore = (& git rev-parse HEAD).Trim()
$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/raven-native-snapshot-delivery-wrapper-$stamp"
$outDir = Join-Path $repo ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$console = Join-Path $outDir 'console-log.txt'
$resultFile = Join-Path $outDir 'result.txt'
$errorFile = Join-Path $outDir 'error.txt'
New-Item -ItemType Directory -Path $outDir -Force | Out-Null

$transcript = $false
function Stop-LocalTranscript {
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true
    Write-Host 'RAVEN SNAPSHOT DELIVERY CAPTURE WRAPPER - START'
    Write-Host "head_before=$headBefore"

    $innerArgs = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $inner,
        '-GameRoot', $GameRoot,
        '-StartupTimeoutSeconds', [string]$StartupTimeoutSeconds,
        '-MainMenuSettleSeconds', [string]$MainMenuSettleSeconds
    )
    & pwsh @innerArgs
    $innerExit = $LASTEXITCODE

    if ($innerExit -eq 0) {
        Stop-LocalTranscript
        Remove-Item -LiteralPath $outDir -Recurse -Force
        Write-Host 'RAVEN_SNAPSHOT_DELIVERY_WRAPPER_PASSED inner_runner_archived_success=true'
        exit 0
    }

    $headAfter = (& git rev-parse HEAD).Trim()
    if ($headAfter -ne $headBefore) {
        Stop-LocalTranscript
        Remove-Item -LiteralPath $outDir -Recurse -Force
        Write-Host "RAVEN_SNAPSHOT_DELIVERY_WRAPPER_FAILED inner_runner_archived_failure=true head_after=$headAfter"
        exit $innerExit
    }

    throw "Inner live-proof runner failed before archiving evidence. exit=$innerExit"
}
catch {
    $outer = $_
    try { $outer.Exception.ToString() | Set-Content -LiteralPath $errorFile -Encoding UTF8 } catch {}
    try {
        @(
            'result=RAVEN_NATIVE_SNAPSHOT_DELIVERY_WRAPPER_FAILED'
            "timestamp=$(Get-Date -Format o)"
            "branch=$ExpectedBranch"
            "head_before=$headBefore"
            "reason=$($outer.Exception.Message)"
            'inner_runner_archived_failure=false'
        ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
    } catch {}
    Write-Host "RAVEN_NATIVE_SNAPSHOT_DELIVERY_WRAPPER_FAILED: $($outer.Exception.Message)"
    Stop-LocalTranscript
    try {
        & git add -f -- $relativeDir
        if ($LASTEXITCODE -ne 0) { throw 'git add wrapper evidence failed.' }
        & git commit -m "test(v0.10.5): archive early Raven live-proof failure $stamp" -- $relativeDir | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git commit wrapper evidence failed.' }
        & git push origin $ExpectedBranch | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'git push wrapper evidence failed.' }
        Write-Host "Early failure evidence pushed: $relativeDir"
    }
    catch {
        Write-Host "WRAPPER_FAILURE_EVIDENCE_PUSH_FAILED: $($_.Exception.Message)"
    }
    exit 1
}
finally {
    Stop-LocalTranscript
}
