$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
. (Join-Path $repo 'tools\v0.10.5\raven-native-bridge-runner-support.ps1')

$zero = Compare-RavenBridgeLog -Before @('old') -After @('old')
if (@($zero.Lines).Count -ne 0 -or -not $zero.PrefixMatches) {
    throw 'Zero-line regression failed.'
}
$one = Compare-RavenBridgeLog -Before @('old') -After @('old', 'RAVEN_NATIVE_BRIDGE_PROXY_LOADED')
if (@($one.Lines).Count -ne 1 -or @($one.Lines)[0] -ne 'RAVEN_NATIVE_BRIDGE_PROXY_LOADED') {
    throw 'One-line scalar regression failed.'
}
$multiple = Compare-RavenBridgeLog -Before @('old') -After @(
    'old',
    'RAVEN_NATIVE_BRIDGE_PROXY_LOADED',
    'RAVEN_NATIVE_BRIDGE_XINPUT_FORWARDED exports=15 success=true'
)
if (@($multiple.Lines).Count -ne 2) { throw 'Multiple-line regression failed.' }
$changed = Compare-RavenBridgeLog -Before @('old') -After @('different')
if ($changed.PrefixMatches -or @($changed.Lines).Count -ne 1) {
    throw 'Changed-prefix regression failed.'
}

$earlyExit = Test-RavenBridgeStartupObservation -ProcessRunning $false -FreshLines @()
if ($earlyExit.Ready -or $earlyExit.Reason -ne 'game_exited_before_bridge_startup') {
    throw 'Early-exit regression failed.'
}
$runningNoLog = Test-RavenBridgeStartupObservation -ProcessRunning $true -FreshLines @()
if ($runningNoLog.Ready -or $runningNoLog.Reason -ne 'expected_fresh_bridge_log_missing') {
    throw 'Missing-log regression failed.'
}
$started = Test-RavenBridgeStartupObservation -ProcessRunning $true -FreshLines @(
    'RAVEN_NATIVE_BRIDGE_PROXY_LOADED target=XINPUT1_4.dll real=system32'
)
if (-not $started.Ready) { throw 'Startup-log regression failed.' }
$proofWithLoader = Test-RavenBridgeProofLines -Lines @(
    'RAVEN_NATIVE_BRIDGE_XINPUT_FORWARDED exports=15 success=true'
) -LoaderLines @(
    '[info] [CompletionistMap v0.10.5-all-ravens] API installed=true catalogueCount=53'
)
if (-not $proofWithLoader.Forwarded -or -not $proofWithLoader.ScriptLoader) {
    throw 'Script Loader evidence regression failed.'
}

$rollbackCalls = 0
$didRollback = Invoke-RavenBridgeFailureRollback -Installed $true -RolledBack $false -Rollback {
    $script:rollbackCalls++
}
if (-not $didRollback -or $rollbackCalls -ne 1) {
    throw 'Failed-startup rollback regression failed.'
}
$didRollbackAgain = Invoke-RavenBridgeFailureRollback -Installed $true -RolledBack $true -Rollback {
    $script:rollbackCalls++
}
if ($didRollbackAgain -or $rollbackCalls -ne 1) {
    throw 'Duplicate rollback regression failed.'
}

Write-Host 'RAVEN_NATIVE_BRIDGE_RUNNER_TESTS_PASSED zero=true one=true multiple=true early_exit=true missing_log=true script_loader=true rollback=true'
