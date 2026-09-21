Set-StrictMode -Version Latest

function Compare-RavenBridgeLog {
    param(
        [AllowEmptyCollection()][string[]]$Before = @(),
        [AllowEmptyCollection()][string[]]$After = @()
    )
    $beforeLines = @($Before)
    $afterLines = @($After)
    $prefixMatches = @($beforeLines).Count -le @($afterLines).Count
    if ($prefixMatches) {
        for ($index = 0; $index -lt @($beforeLines).Count; $index++) {
            if ($beforeLines[$index] -cne $afterLines[$index]) {
                $prefixMatches = $false
                break
            }
        }
    }
    $freshLines = if ($prefixMatches) {
        @($afterLines | Select-Object -Skip @($beforeLines).Count)
    } else {
        @($afterLines)
    }
    return [pscustomobject]@{
        PrefixMatches = [bool]$prefixMatches
        Lines = [string[]]@($freshLines)
    }
}

function Test-RavenBridgeProofLines {
    param(
        [AllowEmptyCollection()][string[]]$Lines = @(),
        [AllowEmptyCollection()][string[]]$LoaderLines = @()
    )
    $safeLines = @($Lines)
    $safeLoaderLines = @($LoaderLines)
    return [pscustomobject]@{
        ProxyLoaded = @($safeLines | Select-String -SimpleMatch 'RAVEN_NATIVE_BRIDGE_PROXY_LOADED').Count -gt 0
        Forwarded = @($safeLines | Select-String -Pattern 'RAVEN_NATIVE_BRIDGE_XINPUT_FORWARDED .*exports=15 success=true').Count -gt 0
        ExeAccepted = @($safeLines | Select-String -SimpleMatch 'RAVEN_NATIVE_BRIDGE_EXE_ACCEPTED').Count -gt 0
        SnapshotAccepted = @($safeLines | Select-String -Pattern 'RAVEN_NATIVE_BRIDGE_SNAPSHOT_ACCEPTED .*count=53 unknown=0').Count -gt 0
        DeliveryPending = @($safeLines | Select-String -SimpleMatch 'RAVEN_NATIVE_BRIDGE_DELIVERY_PENDING').Count -gt 0
        ScriptLoader = @($safeLoaderLines | Select-String -Pattern '\[CompletionistMap v0\.10\.5-all-ravens\] API installed=true').Count -gt 0
    }
}

function Test-RavenBridgeStartupObservation {
    param(
        [bool]$ProcessRunning,
        [AllowEmptyCollection()][string[]]$FreshLines = @()
    )
    $proof = Test-RavenBridgeProofLines -Lines @($FreshLines)
    if ($proof.ProxyLoaded) {
        return [pscustomobject]@{ Ready = $true; Reason = 'proxy_log_observed' }
    }
    if (-not $ProcessRunning) {
        return [pscustomobject]@{ Ready = $false; Reason = 'game_exited_before_bridge_startup' }
    }
    return [pscustomobject]@{ Ready = $false; Reason = 'expected_fresh_bridge_log_missing' }
}

function Invoke-RavenBridgeFailureRollback {
    param(
        [bool]$Installed,
        [bool]$RolledBack,
        [Parameter(Mandatory)][scriptblock]$Rollback
    )
    if (-not $Installed -or $RolledBack) { return $false }
    & $Rollback
    return $true
}
