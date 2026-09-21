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
        ProxyLoaded = @($safeLines | Select-String -Pattern 'RAVEN_NATIVE_BRIDGE_PROXY_LOADED target=dxgi\.dll real=system32').Count -gt 0
        Forwarded = @($safeLines | Select-String -Pattern 'RAVEN_NATIVE_BRIDGE_DXGI_FORWARDED .*exports=20 success=true').Count -gt 0
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
    if ($proof.ProxyLoaded -and $ProcessRunning) {
        return [pscustomobject]@{ Ready = $true; Reason = 'proxy_log_and_live_game_observed' }
    }
    if ($proof.ProxyLoaded -and -not $ProcessRunning) {
        return [pscustomobject]@{ Ready = $false; Reason = 'proxy_log_observed_waiting_for_game_process' }
    }
    if (-not $ProcessRunning) {
        return [pscustomobject]@{ Ready = $false; Reason = 'waiting_for_game_process' }
    }
    return [pscustomobject]@{ Ready = $false; Reason = 'expected_fresh_bridge_log_missing' }
}

function Test-RavenSnapshotDeliveryProofLines {
    param(
        [AllowEmptyCollection()][string[]]$BridgeLines = @(),
        [AllowEmptyCollection()][string[]]$LoaderLines = @()
    )
    $safeBridge = @($BridgeLines)
    $safeLoader = @($LoaderLines)
    $deliveryReady = @($safeBridge | Select-String -Pattern (
        'RAVEN_NATIVE_BRIDGE_DELIVERY_READY mechanism=loopback_socket ' +
        'address=127\.0\.0\.1 port=43753 static_descriptor_writes=false'))
    $advancedIndex = -1
    $eventIndex = -1
    $reopenIndex = -1
    $freshIndex = -1
    for ($index = 0; $index -lt $safeLoader.Count; $index++) {
        $line = [string]$safeLoader[$index]
        if ($advancedIndex -lt 0 -and
            $line -match '\[CompletionistMap v0\.10\.5-all-ravens\] NATIVE_AUTHORITY_APPLIED .*killed=27 alive=26') {
            $advancedIndex = $index
            continue
        }
        if ($advancedIndex -ge 0 -and $eventIndex -lt 0 -and
            $line -match '\[CompletionistMap v0\.10\.5-all-ravens\] STATE .*collected=true source=OnHitByWeapon(?:\s|$)') {
            $eventIndex = $index
            continue
        }
        if ($eventIndex -ge 0 -and $reopenIndex -lt 0 -and
            $line -match '\[CompletionistMap v0\.10\.5-all-ravens\] NATIVE_AUTHORITY_REFRESH source=map_create ') {
            $reopenIndex = $index
            continue
        }
        if ($reopenIndex -ge 0 -and $freshIndex -lt 0 -and
            $line -match '\[CompletionistMap v0\.10\.5-all-ravens\] NATIVE_AUTHORITY_APPLIED .*killed=0 alive=53') {
            $freshIndex = $index
        }
    }
    return [pscustomobject]@{
        DeliveryReady = @($deliveryReady).Count -gt 0
        AdvancedApplied = $advancedIndex -ge 0
        ImmediateEvent = $eventIndex -ge 0
        MapReopenObserved = $reopenIndex -ge 0
        FreshApplied = $freshIndex -ge 0
        Ordered = $advancedIndex -ge 0 -and $eventIndex -gt $advancedIndex -and
            $reopenIndex -gt $eventIndex -and $freshIndex -gt $reopenIndex
    }
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
