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

function Test-RavenSnapshotDeliveryProofLines(
    [string[]]$BridgeLines,
    [string[]]$LoaderLines
) {
    $safeBridge = @($BridgeLines | Where-Object {
        $_ -notmatch 'WriteProcessMemory|NtWriteVirtualMemory|VirtualAllocEx|VirtualProtectEx|CreateRemoteThread|QueueUserAPC|SetThreadContext|DebugActiveProcess'
    })
    $deliveryReady = @($safeBridge | Select-String -Pattern (
        'RAVEN_NATIVE_BRIDGE_DELIVERY_READY mechanism=loopback_socket .*' +
        'static_descriptor_writes=false save_writes=false progression_writes=false'))

    $parseAuthority = {
        param([string]$Line)
        if ($Line -match (
            '\[CompletionistMap v0\.10\.5-all-ravens\] NATIVE_AUTHORITY_APPLIED ' +
            '.*killed=([0-9]+) alive=([0-9]+).*postBoundary=(true|false) ' +
            'boundaryEpoch=([0-9]+) restoreEpoch=([0-9]+) authority=([^ ]+)')) {
            return [pscustomobject]@{
                Killed = [int]$Matches[1]
                Alive = [int]$Matches[2]
                PostBoundary = $Matches[3] -eq 'true'
                BoundaryEpoch = [uint64]$Matches[4]
                RestoreEpoch = [uint64]$Matches[5]
                Authority = [string]$Matches[6]
                Derived = $false
            }
        }
        if ($Line -match (
            '\[CompletionistMap v0\.10\.5-all-ravens\] NATIVE_AUTHORITY_DERIVED ' +
            '.*finalKilled=([0-9]+) finalAlive=([0-9]+).*postBoundary=(true|false) ' +
            'boundaryEpoch=([0-9]+) restoreEpoch=([0-9]+) authority=([^ ]+)')) {
            return [pscustomobject]@{
                Killed = [int]$Matches[1]
                Alive = [int]$Matches[2]
                PostBoundary = $Matches[3] -eq 'true'
                BoundaryEpoch = [uint64]$Matches[4]
                RestoreEpoch = [uint64]$Matches[5]
                Authority = [string]$Matches[6]
                Derived = $true
            }
        }
        return $null
    }

    $Lines = @($LoaderLines)

    # Restore/start callbacks can legitimately emit positive kill notes for
    # Ravens that were already dead. They are not the manual gameplay kill
    # under test. Anchor the proof to the exact OnHitByWeapon delivery.
    $gameplayKillLoaderIndex = -1
    $gameplayKillCatalogueId = $null
    $bridgeKillEpoch = $null
    for ($index = 0; $index -lt $Lines.Count; $index++) {
        $line = [string]$Lines[$index]
        if ($line -match (
            '\[CompletionistMap v0\.10\.5-raven-events\] BRIDGE_KILL_NOTE ' +
            'source=OnHitByWeapon catalogueId=([^ ]+) delivered=true ' +
            'detail=RAVEN_NOTE_V1 OK kind=killed restoreEpoch=([0-9]+) ')) {
            $gameplayKillLoaderIndex = $index
            $gameplayKillCatalogueId = [string]$Matches[1]
            $bridgeKillEpoch = [uint64]$Matches[2]
            break
        }
    }

    $bridgeKillIndex = -1
    if ($gameplayKillLoaderIndex -ge 0) {
        $escapedId = [regex]::Escape($gameplayKillCatalogueId)
        for ($index = 0; $index -lt $safeBridge.Count; $index++) {
            $line = [string]$safeBridge[$index]
            if ($line -match (
                'RAVEN_NATIVE_BRIDGE_KILL_NOTED catalogueId=' + $escapedId +
                ' restoreEpoch=' + [string]$bridgeKillEpoch + ' ')) {
                $bridgeKillIndex = $index
                break
            }
        }
    }

    $bridgeBoundaryEpochs = New-Object System.Collections.Generic.List[uint64]
    if ($null -ne $bridgeKillEpoch) {
        foreach ($lineValue in $safeBridge) {
            $line = [string]$lineValue
            if ($line -match 'RAVEN_NATIVE_BRIDGE_BOUNDARY_NOTED restoreEpoch=([0-9]+) advanced=true ') {
                $epoch = [uint64]$Matches[1]
                if ($epoch -gt [uint64]$bridgeKillEpoch -and
                    -not $bridgeBoundaryEpochs.Contains($epoch)) {
                    $bridgeBoundaryEpochs.Add($epoch)
                }
            }
        }
    }

    $advancedIndex = -1
    $advancedKilled = $null
    $advancedAlive = $null
    $advancedDerived = $false
    $killBaselineIndex = -1
    $killBaselineKilled = $null
    $killBaselineAlive = $null
    $killBaselineDerived = $false
    $reopenIndex = -1
    $checkpointBoundaryIndex = -1
    $checkpointApplyIndex = -1
    $freshBoundaryIndex = -1
    $freshIndex = -1
    $checkpointEpoch = $null
    $freshEpoch = $null
    $checkpointEpochMatched = $false
    $freshEpochMatched = $false

    for ($index = 0; $index -lt $Lines.Count; $index++) {
        $line = [string]$Lines[$index]
        $authority = & $parseAuthority $line

        if ($advancedIndex -lt 0 -and $null -ne $authority -and
            $authority.Killed + $authority.Alive -eq 53) {
            $advancedIndex = $index
            $advancedKilled = [int]$authority.Killed
            $advancedAlive = [int]$authority.Alive
            $advancedDerived = [bool]$authority.Derived
        }

        if ($gameplayKillLoaderIndex -ge 0 -and $index -lt $gameplayKillLoaderIndex -and
            $null -ne $authority -and
            $authority.Killed + $authority.Alive -eq 53) {
            $killBaselineIndex = $index
            $killBaselineKilled = [int]$authority.Killed
            $killBaselineAlive = [int]$authority.Alive
            $killBaselineDerived = [bool]$authority.Derived
        }

        if ($gameplayKillLoaderIndex -ge 0 -and $index -gt $gameplayKillLoaderIndex -and
            $killBaselineIndex -ge 0 -and $reopenIndex -lt 0 -and
            $null -ne $authority -and -not $authority.PostBoundary -and
            $authority.Killed -eq $killBaselineKilled + 1 -and
            $authority.Alive -eq $killBaselineAlive - 1 -and
            $authority.RestoreEpoch -eq [uint64]$bridgeKillEpoch) {
            $reopenIndex = $index
        }

        if ($gameplayKillLoaderIndex -ge 0 -and $index -gt $gameplayKillLoaderIndex -and
            $checkpointBoundaryIndex -lt 0 -and
            $line -match '\[CompletionistMap v0\.10\.5-all-ravens\] AUTHORITY_BOUNDARY .*source=native_restore_epoch .*boundaryEpoch=([0-9]+) .*captureReady=true ') {
            $candidateEpoch = [uint64]$Matches[1]
            if ($bridgeBoundaryEpochs.Contains($candidateEpoch)) {
                $checkpointBoundaryIndex = $index
                $checkpointEpoch = $candidateEpoch
            }
        }

        if ($checkpointBoundaryIndex -ge 0 -and $index -gt $checkpointBoundaryIndex -and
            $checkpointApplyIndex -lt 0 -and $killBaselineIndex -ge 0 -and
            $null -ne $authority -and $authority.PostBoundary -and
            $authority.Killed -eq $killBaselineKilled + 1 -and
            $authority.Alive -eq $killBaselineAlive - 1 -and
            $null -ne $checkpointEpoch -and
            $authority.BoundaryEpoch -eq [uint64]$checkpointEpoch -and
            $authority.RestoreEpoch -eq [uint64]$checkpointEpoch) {
            $checkpointApplyIndex = $index
            $checkpointEpochMatched = $true
        }

        if ($checkpointApplyIndex -ge 0 -and $index -gt $checkpointApplyIndex -and
            $freshBoundaryIndex -lt 0 -and
            $line -match '\[CompletionistMap v0\.10\.5-all-ravens\] AUTHORITY_BOUNDARY .*source=native_restore_epoch .*boundaryEpoch=([0-9]+) .*captureReady=true ') {
            $candidateEpoch = [uint64]$Matches[1]
            if ($candidateEpoch -gt [uint64]$checkpointEpoch -and
                $bridgeBoundaryEpochs.Contains($candidateEpoch)) {
                $freshBoundaryIndex = $index
                $freshEpoch = $candidateEpoch
            }
        }

        if ($freshBoundaryIndex -ge 0 -and $index -gt $freshBoundaryIndex -and
            $freshIndex -lt 0 -and
            $null -ne $authority -and $authority.PostBoundary -and
            $authority.Killed -eq 0 -and $authority.Alive -eq 53 -and
            $null -ne $freshEpoch -and
            $authority.BoundaryEpoch -eq [uint64]$freshEpoch -and
            $authority.RestoreEpoch -eq [uint64]$freshEpoch) {
            $freshIndex = $index
            $freshEpochMatched = $true
        }
    }

    $bridgeOrdered = $bridgeKillIndex -ge 0 -and
        $bridgeBoundaryEpochs.Count -ge 2 -and
        $bridgeBoundaryEpochs[0] -gt [uint64]$bridgeKillEpoch -and
        $bridgeBoundaryEpochs[1] -gt $bridgeBoundaryEpochs[0]
    $loaderOrdered = $advancedIndex -ge 0 -and
        $killBaselineIndex -ge $advancedIndex -and
        $gameplayKillLoaderIndex -gt $killBaselineIndex -and
        $checkpointBoundaryIndex -gt $gameplayKillLoaderIndex -and
        $checkpointApplyIndex -gt $checkpointBoundaryIndex -and
        $freshBoundaryIndex -gt $checkpointApplyIndex -and
        $freshIndex -gt $freshBoundaryIndex -and
        ($reopenIndex -lt 0 -or
         ($reopenIndex -gt $gameplayKillLoaderIndex -and
          $reopenIndex -lt $checkpointBoundaryIndex))

    return [pscustomobject]@{
        DeliveryReady = @($deliveryReady).Count -gt 0
        AdvancedApplied = $advancedIndex -ge 0
        AdvancedKilled = $advancedKilled
        AdvancedAlive = $advancedAlive
        AdvancedDerived = $advancedDerived
        ImmediateEvent = $gameplayKillLoaderIndex -ge 0 -and $bridgeKillIndex -ge 0
        ImmediateKillEpoch = $bridgeKillEpoch
        GameplayKillCatalogueId = $gameplayKillCatalogueId
        KillBaselineKilled = $killBaselineKilled
        KillBaselineAlive = $killBaselineAlive
        KillBaselineDerived = $killBaselineDerived
        MapReopenObserved = $reopenIndex -ge 0
        CheckpointBoundaryObserved = $checkpointBoundaryIndex -ge 0
        PostBoundaryApplied = $checkpointApplyIndex -ge 0
        CheckpointBoundaryEpochMatched = $checkpointEpochMatched
        CheckpointBoundaryEpoch = $checkpointEpoch
        FreshBoundaryObserved = $freshBoundaryIndex -ge 0
        FreshApplied = $freshIndex -ge 0
        FreshBoundaryEpochMatched = $freshEpochMatched
        FreshBoundaryEpoch = $freshEpoch
        Ordered = $bridgeOrdered -and $loaderOrdered
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
