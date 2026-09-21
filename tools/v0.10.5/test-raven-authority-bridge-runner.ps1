$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
. (Join-Path $repo 'tools\v0.10.5\raven-native-bridge-runner-support.ps1')

$zero = Compare-RavenBridgeLog -Before @('old') -After @('old')
if (@($zero.Lines).Count -ne 0 -or -not $zero.PrefixMatches) {
    throw 'Zero-line regression failed.'
}

$one = Compare-RavenBridgeLog -Before @('old') -After @(
    'old',
    'RAVEN_NATIVE_BRIDGE_PROXY_LOADED target=dxgi.dll real=system32 save_writes=false progression_writes=false'
)
if (@($one.Lines).Count -ne 1) {
    throw 'One-line scalar regression failed.'
}

$multiple = Compare-RavenBridgeLog -Before @('old') -After @(
    'old',
    'RAVEN_NATIVE_BRIDGE_PROXY_LOADED target=dxgi.dll real=system32 save_writes=false progression_writes=false',
    'RAVEN_NATIVE_BRIDGE_DXGI_FORWARDED exports=20 success=true'
)
if (@($multiple.Lines).Count -ne 2) { throw 'Multiple-line regression failed.' }

$changed = Compare-RavenBridgeLog -Before @('old') -After @('different')
if ($changed.PrefixMatches -or @($changed.Lines).Count -ne 1) {
    throw 'Changed-prefix regression failed.'
}

$handoffGap = Test-RavenBridgeStartupObservation -ProcessRunning $false -FreshLines @()
if ($handoffGap.Ready -or $handoffGap.Reason -ne 'waiting_for_game_process') {
    throw 'Steam handoff gap regression failed.'
}

$proxyBeforeSuccessor = Test-RavenBridgeStartupObservation -ProcessRunning $false -FreshLines @(
    'RAVEN_NATIVE_BRIDGE_PROXY_LOADED target=dxgi.dll real=system32 save_writes=false progression_writes=false'
)
if ($proxyBeforeSuccessor.Ready -or $proxyBeforeSuccessor.Reason -ne 'proxy_log_observed_waiting_for_game_process') {
    throw 'Proxy-before-successor regression failed.'
}

$runningNoLog = Test-RavenBridgeStartupObservation -ProcessRunning $true -FreshLines @()
if ($runningNoLog.Ready -or $runningNoLog.Reason -ne 'expected_fresh_bridge_log_missing') {
    throw 'Missing-log regression failed.'
}

$started = Test-RavenBridgeStartupObservation -ProcessRunning $true -FreshLines @(
    'RAVEN_NATIVE_BRIDGE_PROXY_LOADED target=dxgi.dll real=system32 save_writes=false progression_writes=false'
)
if (-not $started.Ready -or $started.Reason -ne 'proxy_log_and_live_game_observed') {
    throw 'Startup-log plus live-process regression failed.'
}

$proofWithLoader = Test-RavenBridgeProofLines -Lines @(
    'RAVEN_NATIVE_BRIDGE_PROXY_LOADED target=dxgi.dll real=system32 save_writes=false progression_writes=false',
    'RAVEN_NATIVE_BRIDGE_DXGI_FORWARDED exports=20 success=true',
    'RAVEN_NATIVE_BRIDGE_EXE_ACCEPTED sha256=caebcb027980d7eac9203d190f9ee649eebc549f8defce138e2114dc91f40452',
    'RAVEN_NATIVE_BRIDGE_SNAPSHOT_ACCEPTED count=53 unknown=0',
    'RAVEN_NATIVE_BRIDGE_DELIVERY_PENDING'
) -LoaderLines @(
    '[info] [CompletionistMap v0.10.5-all-ravens] API installed=true catalogueCount=53'
)
if (-not $proofWithLoader.ProxyLoaded -or
    -not $proofWithLoader.Forwarded -or
    -not $proofWithLoader.ExeAccepted -or
    -not $proofWithLoader.SnapshotAccepted -or
    -not $proofWithLoader.DeliveryPending -or
    -not $proofWithLoader.ScriptLoader) {
    throw 'DXGI proof-line regression failed.'
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

Write-Host 'RAVEN_NATIVE_BRIDGE_RUNNER_TESTS_PASSED target=dxgi.dll zero=true one=true multiple=true steam_handoff=true proxy_before_successor=true missing_log=true dxgi_forwarding=true script_loader=true rollback=true'
