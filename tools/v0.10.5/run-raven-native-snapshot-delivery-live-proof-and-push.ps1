param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [ValidateRange(30, 180)][int]$StartupTimeoutSeconds = 90,
    [ValidateRange(20, 90)][int]$MainMenuSettleSeconds = 40,
    [string]$ExpectedBranch = 'codex/all-ravens-release-candidate',
    [switch]$MapVisibilityOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo
if ((& git branch --show-current).Trim() -ne $ExpectedBranch) { throw "Need branch $ExpectedBranch." }
if (@(& git status --porcelain --untracked-files=no).Count -gt 0) { throw 'Tracked tree must be clean.' }
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
    throw 'Close God of War first.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$exe = Join-Path $game 'GoW.exe'
$version = Join-Path $game 'version.dll'
$proxy = Join-Path $game 'dxgi.dll'
$bridgeManifest = Join-Path $game 'mods\completionist-map\native\raven-native-bridge-manifest.json'
$bridgeOperation = Join-Path $game 'mods\completionist-map\native\raven-native-bridge-operation.json'
$bridgeLog = Join-Path $game 'mods\completionist-map\native\raven-native-bridge.log'
$loaderLog = Join-Path $game 'mods\loader_log.txt'
$offlineGate = Join-Path $repo 'tools\v0.10.5\test-raven-native-snapshot-delivery-offline-gates.ps1'
$installBridge = Join-Path $repo 'tools\v0.10.5\install-raven-authority-bridge.ps1'
$rollbackBridge = Join-Path $repo 'tools\v0.10.5\rollback-raven-authority-bridge.ps1'
$support = Join-Path $repo 'tools\v0.10.5\raven-native-bridge-runner-support.ps1'
$engine = Join-Path $repo 'tools\v0.10.4\nornir-runtime-candidate3.ps1'
$proofPath = Join-Path $repo 'archive\all-ravens\all-ravens-release-candidate-offline.json'
$worktreeCandidateRoot = Join-Path $repo 'build\v0.10.5-all-ravens-release-candidate\offline\candidate\game-root'
$candidateRoot = $worktreeCandidateRoot
$prepareCandidate = Join-Path $repo 'tools\v0.10.5\prepare-all-ravens-delivery-candidate.py'

foreach ($required in @($exe,$version,$offlineGate,$installBridge,$rollbackBridge,$support,$engine,$proofPath,$prepareCandidate)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Need live-proof file: $required" }
}
. $support

$engineText = [IO.File]::ReadAllText($engine).Replace("`r`n", "`n").Replace("`r", "`n")
$engineHash = [Convert]::ToHexString(
    [Security.Cryptography.SHA256]::HashData([Text.Encoding]::UTF8.GetBytes($engineText))
).ToLowerInvariant()
if ($engineHash -ne '83f11f8e3a5b6e56ad5d06ba22baa779f91c986ace42ab3017de2b2231d7057a') {
    throw 'Transaction engine canonical SHA differs.'
}
$RunnerExpectedBranch = $ExpectedBranch
. $engine -LibraryOnly
# The v0.10.4 transaction engine defines its own $ExpectedBranch when
# dot-sourced. Restore this runner's caller-selected branch contract
# immediately afterwards so evidence/result metadata and pushes stay on the
# intended Raven branch.
$ExpectedBranch = $RunnerExpectedBranch

$pythonExe = 'python.exe'
$pythonPrefix = @()
& py.exe -3.14 -c 'import sys' 2>$null
if ($LASTEXITCODE -eq 0) {
    $pythonExe = 'py.exe'
    $pythonPrefix = @('-3.14')
}
$prepareLines = @(& $pythonExe @pythonPrefix $prepareCandidate 2>&1)
$prepareExit = $LASTEXITCODE
$prepareLines | ForEach-Object { Write-Host $_ }
if ($prepareExit -ne 0) { throw 'Could not prepare pinned All-Ravens delivery candidate.' }
$rootPrefix = 'ALL_RAVENS_NATIVE_DELIVERY_CANDIDATE_ROOT='
$rootLines = @($prepareLines | Where-Object { ([string]$_).StartsWith($rootPrefix, [StringComparison]::Ordinal) })
if ($rootLines.Count -ne 1) { throw 'Candidate preparer did not report exactly one canonical output root.' }
$preparedCandidateRoot = [IO.Path]::GetFullPath(([string]$rootLines[0]).Substring($rootPrefix.Length))

$files = [ordered]@{
    mapmaster = 'exec/dc/pc_le/mapmaster.dcb'
    mapcoords = 'exec/dc/pc_le/mapcoords.dcb'
    ui = 'exec/dc/pc_le/wad_r_ui.dcb'
    mapmenu = 'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
    events = 'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua'
}
$candidateProof = Get-Content -LiteralPath $proofPath -Raw | ConvertFrom-Json
if ($candidateProof.ready_for_runtime_test -ne $true -or
    $candidateProof.result -ne 'ALL_RAVENS_OFFLINE_CANDIDATE_BUILT_NATIVE_DELIVERY_GATE_READY') {
    throw 'All-Ravens native delivery proof gate differs.'
}
$candidateShas = [ordered]@{}
$repoBuildRoot = [IO.Path]::GetFullPath((Join-Path $repo 'build'))
$preparedInsideWorktreeBuild = Test-PathWithin -Parent $repoBuildRoot -Child $preparedCandidateRoot

if ($preparedInsideWorktreeBuild) {
    $candidateRoot = $preparedCandidateRoot
}
else {
    $candidateRoot = [IO.Path]::GetFullPath($worktreeCandidateRoot)
    if (-not (Test-PathWithin -Parent $repoBuildRoot -Child $candidateRoot)) {
        throw 'Normalized candidate root escaped this worktree build tree.'
    }
    if (Test-Path -LiteralPath $candidateRoot) {
        Remove-Item -LiteralPath $candidateRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $candidateRoot | Out-Null
    Write-Host "Candidate preparer resolved outside this worktree build tree; mirroring five verified files."
    Write-Host "Prepared root: $preparedCandidateRoot"
    Write-Host "Worktree root: $candidateRoot"
}

foreach ($name in $files.Keys) {
    $relative = [string]$files[$name]
    $entry = $candidateProof.files.PSObject.Properties[$relative]
    if ($null -eq $entry) { throw "Candidate proof misses: $relative" }

    $preparedPath = Resolve-SafeChildPath -Root $preparedCandidateRoot -Relative $relative -Label 'prepared candidate source'
    if (-not (Test-Path -LiteralPath $preparedPath -PathType Leaf)) {
        throw "Prepared candidate misses: $relative root=$preparedCandidateRoot"
    }
    $preparedHash = (Get-FileHash -LiteralPath $preparedPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($preparedHash -ne [string]$entry.Value.sha256) {
        throw "Prepared candidate SHA differs: $relative"
    }

    $path = Resolve-SafeChildPath -Root $candidateRoot -Relative $relative -Label 'worktree candidate'
    if (-not $preparedInsideWorktreeBuild) {
        New-Item -ItemType Directory -Force -Path (Split-Path $path -Parent) | Out-Null
        Copy-Item -LiteralPath $preparedPath -Destination $path -Force
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Candidate normalization failed: $relative root=$candidateRoot"
    }
    $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($hash -ne [string]$entry.Value.sha256) { throw "Candidate SHA differs: $relative" }
    $candidateShas[$name] = $hash
}
Write-Host "RAVEN_DELIVERY_CANDIDATE_PATH_READY root=$candidateRoot files=$($candidateShas.Count)"

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/raven-native-snapshot-delivery-live-proof-$stamp"
$outDir = Join-Path $repo ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$stateRoot = Join-Path $repo "build\v0.10.5-all-ravens-release-candidate\runtime\delivery-live-$stamp"
$activeManifest = Join-Path $stateRoot 'active.json'
$console = Join-Path $outDir 'console-log.txt'
$resultFile = Join-Path $outDir 'result.txt'

function Get-LowerHash([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-GameFileSnapshot {
    $snapshot = [ordered]@{}
    foreach ($name in $files.Keys) {
        $path = Join-Path $game ([string]$files[$name])
        $exists = Test-Path -LiteralPath $path -PathType Leaf
        $snapshot[$name] = [ordered]@{
            exists = $exists
            sha256 = if ($exists) { Get-LowerHash $path } else { $null }
        }
    }
    return $snapshot
}

function Test-GameFileSnapshot([System.Collections.IDictionary]$Expected) {
    foreach ($name in $files.Keys) {
        $path = Join-Path $game ([string]$files[$name])
        $exists = Test-Path -LiteralPath $path -PathType Leaf
        if ($exists -ne [bool]$Expected[$name].exists) { return $false }
        if ($exists -and (Get-LowerHash $path) -ne [string]$Expected[$name].sha256) { return $false }
    }
    return $true
}

if (Test-Path -LiteralPath $bridgeOperation -PathType Leaf) {
    throw 'Unfinished Raven bridge operation journal exists before live proof. Run startup recovery first.'
}
$mapBefore = Get-GameFileSnapshot
$proxyBeforeExists = Test-Path -LiteralPath $proxy -PathType Leaf
$manifestBeforeExists = Test-Path -LiteralPath $bridgeManifest -PathType Leaf
$proxyBeforeHash = if ($proxyBeforeExists) { Get-LowerHash $proxy } else { $null }
$manifestBeforeHash = if ($manifestBeforeExists) { Get-LowerHash $bridgeManifest } else { $null }
$versionBefore = Get-LowerHash $version
$bridgeBeforeLines = if (Test-Path -LiteralPath $bridgeLog -PathType Leaf) { @(Get-Content -LiteralPath $bridgeLog) } else { @() }
$loaderBeforeLines = if (Test-Path -LiteralPath $loaderLog -PathType Leaf) { @(Get-Content -LiteralPath $loaderLog) } else { @() }

$transcript = $false
$bridgeInstalled = $false
$mapInstalled = $false
$bridgeRolledBack = $false
$mapRolledBack = $false
$launched = $false
$published = $false
$checkpointReloadAccepted = $false
$crossSaveRevivalAccepted = $false
$sameMapReaddAccepted = $false
$mapVisibilityAccepted = $false
$mapManifest = $null
$gameProcess = $null

function Stop-LocalTranscript {
    if ($script:transcript) {
        Stop-Transcript | Out-Null
        $script:transcript = $false
    }
}

function Stop-GoWProcesses {
    @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }) |
        Stop-Process -Force -ErrorAction SilentlyContinue
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -eq 0) { return }
        Start-Sleep -Milliseconds 250
    }
    throw 'GoW process remained alive after stop request.'
}

function Test-BridgeRollbackState {
    $proxyAfterExists = Test-Path -LiteralPath $proxy -PathType Leaf
    $manifestAfterExists = Test-Path -LiteralPath $bridgeManifest -PathType Leaf
    if ($proxyAfterExists -ne $proxyBeforeExists -or $manifestAfterExists -ne $manifestBeforeExists) { return $false }
    if ($proxyAfterExists -and (Get-LowerHash $proxy) -ne $proxyBeforeHash) { return $false }
    if ($manifestAfterExists -and (Get-LowerHash $bridgeManifest) -ne $manifestBeforeHash) { return $false }
    if (Test-Path -LiteralPath $bridgeOperation -PathType Leaf) { return $false }
    return (Get-LowerHash $version) -eq $versionBefore
}

function Get-FreshLogs {
    $bridgeAfter = if (Test-Path -LiteralPath $bridgeLog -PathType Leaf) { @(Get-Content -LiteralPath $bridgeLog) } else { @() }
    $loaderAfter = if (Test-Path -LiteralPath $loaderLog -PathType Leaf) { @(Get-Content -LiteralPath $loaderLog) } else { @() }
    $bridgeComparison = Compare-RavenBridgeLog -Before @($bridgeBeforeLines) -After @($bridgeAfter)
    $loaderComparison = Compare-RavenBridgeLog -Before @($loaderBeforeLines) -After @($loaderAfter)
    if (Test-Path -LiteralPath $bridgeLog -PathType Leaf) { Copy-Item -LiteralPath $bridgeLog -Destination (Join-Path $outDir 'bridge-log-full.txt') -Force }
    if (Test-Path -LiteralPath $loaderLog -PathType Leaf) { Copy-Item -LiteralPath $loaderLog -Destination (Join-Path $outDir 'loader-log-full.txt') -Force }
    @($bridgeComparison.Lines) | Set-Content -LiteralPath (Join-Path $outDir 'bridge-log-fresh.txt') -Encoding UTF8
    @($loaderComparison.Lines) | Set-Content -LiteralPath (Join-Path $outDir 'loader-log-fresh.txt') -Encoding UTF8
    return [pscustomobject]@{
        Bridge = [string[]]@($bridgeComparison.Lines)
        Loader = [string[]]@($loaderComparison.Lines)
        BridgePrefix = [bool]$bridgeComparison.PrefixMatches
        LoaderPrefix = [bool]$loaderComparison.PrefixMatches
    }
}

function Restore-MapCandidate {
    if (-not $script:mapInstalled -or $script:mapRolledBack) { return }
    $validated = Get-ValidatedActiveTransaction -Active $activeManifest -Game $game -Candidate $candidateRoot -State $stateRoot -ProofPath $proofPath -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'all-ravens-v0.10.5-native-delivery-live' -RepoBranch $ExpectedBranch
    Restore-State -Manifest $validated -Game $game -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -ProofPath $proofPath -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'all-ravens-v0.10.5-native-delivery-live' -RepoBranch $ExpectedBranch -CheckInstalled $true -Force $false
    $script:mapRolledBack = $true
    $script:mapInstalled = $false
}

function Publish-Proof([string]$Result, [string]$Reason, [object]$Delivery) {
    if ($script:published) { return }
    Stop-LocalTranscript
    $mapExact = Test-GameFileSnapshot $mapBefore
    $bridgeExact = Test-BridgeRollbackState
    @(
        "result=$Result"
        "reason=$Reason"
        "timestamp=$(Get-Date -Format o)"
        "branch=$ExpectedBranch"
        "game_launched=$($script:launched.ToString().ToLowerInvariant())"
        "native_delivery_ready=$($Delivery.DeliveryReady.ToString().ToLowerInvariant())"
        "advanced_authority_applied=$($Delivery.AdvancedApplied.ToString().ToLowerInvariant())"
        "advanced_killed=$($Delivery.AdvancedKilled)"
        "advanced_alive=$($Delivery.AdvancedAlive)"
        "advanced_derived=$($Delivery.AdvancedDerived.ToString().ToLowerInvariant())"
        "immediate_raven_kill_event=$($Delivery.ImmediateEvent.ToString().ToLowerInvariant())"
        "bridge_kill_note_observed=$($Delivery.ImmediateEvent.ToString().ToLowerInvariant())"
        "bridge_kill_restore_epoch=$($Delivery.ImmediateKillEpoch)"
        "gameplay_kill_catalogue_id=$($Delivery.GameplayKillCatalogueId)"
        "kill_baseline_killed=$($Delivery.KillBaselineKilled)"
        "kill_baseline_alive=$($Delivery.KillBaselineAlive)"
        "kill_baseline_derived=$($Delivery.KillBaselineDerived.ToString().ToLowerInvariant())"
        "map_reopen_native_refresh_observed=$($Delivery.MapReopenObserved.ToString().ToLowerInvariant())"
        "checkpoint_authority_boundary_observed=$($Delivery.CheckpointBoundaryObserved.ToString().ToLowerInvariant())"
        "checkpoint_postboundary_snapshot_applied=$($Delivery.PostBoundaryApplied.ToString().ToLowerInvariant())"
        "checkpoint_boundary_epoch_matched=$($Delivery.CheckpointBoundaryEpochMatched.ToString().ToLowerInvariant())"
        "checkpoint_boundary_epoch=$($Delivery.CheckpointBoundaryEpoch)"
        "postkill_save_reload_manual=$($script:checkpointReloadAccepted.ToString().ToLowerInvariant())"
        "immediate_reopen_postkill_save_manual=$($script:checkpointReloadAccepted.ToString().ToLowerInvariant())"
        "cross_save_revival_manual=$($script:crossSaveRevivalAccepted.ToString().ToLowerInvariant())"
        "same_map_readd_no_stock_manual=$($script:sameMapReaddAccepted.ToString().ToLowerInvariant())"
        "map_visibility_only_mode=$($MapVisibilityOnly.ToString().ToLowerInvariant())"
        "map_filter_visibility_manual=$($script:mapVisibilityAccepted.ToString().ToLowerInvariant())"
        "mystic_gateway_visibility_manual=$($script:mapVisibilityAccepted.ToString().ToLowerInvariant())"
        "fresh_boundary_observed=$($Delivery.FreshBoundaryObserved.ToString().ToLowerInvariant())"
        "fresh_boundary_epoch_matched=$($Delivery.FreshBoundaryEpochMatched.ToString().ToLowerInvariant())"
        "fresh_boundary_epoch=$($Delivery.FreshBoundaryEpoch)"
        "fresh_0_killed_applied=$($Delivery.FreshApplied.ToString().ToLowerInvariant())"
        "ordered_acceptance=$($Delivery.Ordered.ToString().ToLowerInvariant())"
        "map_candidate_rollback_exact=$($mapExact.ToString().ToLowerInvariant())"
        "dxgi_manifest_rollback_exact=$($bridgeExact.ToString().ToLowerInvariant())"
        "dxgi_operation_journal_absent=$(((-not (Test-Path -LiteralPath $bridgeOperation -PathType Leaf))).ToString().ToLowerInvariant())"
        "version_dll_untouched=$(((Get-LowerHash $version) -eq $versionBefore).ToString().ToLowerInvariant())"
        'static_descriptor_writes=false'
        'bridge_process_memory_writes=false'
        'bridge_save_writes=false'
        'bridge_progression_writes=false'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
    & git add -f -- $relativeDir
    if ($LASTEXITCODE -ne 0) { throw 'git add proof failed.' }
    & git commit -m "test(v0.10.5): capture Raven snapshot delivery proof $stamp" -- $relativeDir | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git commit proof failed.' }
    & git push origin $ExpectedBranch | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'git push proof failed.' }
    $script:published = $true
}

try {
    New-Item -ItemType Directory -Path $outDir | Out-Null
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $transcript = $true

    Write-Host 'RAVEN SNAPSHOT DELIVERY LIVE PROOF - OFFLINE GATES FIRST'
    & $offlineGate -GameRootFixture $game -ExpectedBranch $ExpectedBranch
    if ($LASTEXITCODE -ne 0) { throw 'Snapshot delivery offline gates failed.' }

    $head = (& git rev-parse HEAD).Trim()
    $mapManifest = Invoke-TransactionalInstall -Game $game -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'all-ravens-v0.10.5-native-delivery-live' -RepoBranch $ExpectedBranch -RepoHead $head -ProofPath $proofPath
    $mapInstalled = $true
    & $installBridge -GameRoot $game
    $bridgeInstalled = $true

    Write-Host 'Candidate and owned DXGI bridge installed. Launching GoW.'
    $baselinePids = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') } | Select-Object -ExpandProperty Id)
    $gameProcess = Start-Process -FilePath $exe -WorkingDirectory $game -PassThru
    $launched = $true
    $deadline = [DateTime]::UtcNow.AddSeconds($StartupTimeoutSeconds)
    $startupReady = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 250
        $live = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') -and $baselinePids -notcontains $_.Id })
        $logs = Get-FreshLogs
        $startup = Test-RavenBridgeStartupObservation -ProcessRunning (@($live).Count -gt 0) -FreshLines @($logs.Bridge)
        $delivery = Test-RavenSnapshotDeliveryProofLines -BridgeLines @($logs.Bridge) -LoaderLines @($logs.Loader)
        if ($startup.Ready -and $delivery.DeliveryReady) { $startupReady = $true; break }
    }
    if (-not $startupReady) { throw 'GoW plus loopback snapshot delivery did not become ready before timeout.' }
    Write-Host "Native delivery ready. Waiting $MainMenuSettleSeconds seconds for main menu."
    Start-Sleep -Seconds $MainMenuSettleSeconds
    if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -eq 0) {
        throw 'GoW exited during main-menu settle.'
    }

    if ($MapVisibilityOnly) {
        $answer = Read-Host 'MAP VISIBILITY CHECK: Load a save with at least one living Raven. On the normal map: (1) Show All must show living Ravens; (2) RAVENS must show living Ravens; (3) switch to at least two non-Raven filters such as Mystic Gateways/Shops/Artefacts and Ravens must disappear immediately; (4) switch back to Show All or RAVENS and only living Ravens must return; (5) close the map, interact with a Mystic Gateway and open its FAST TRAVEL destination map: NO Raven icons may be visible there in any realm. Type MAP_VISIBILITY_OK only if every check passes, or REGRESSION if anything is wrong'
        if ($answer -eq 'REGRESSION') { throw 'Raven map filter or Mystic Gateway visibility regression reported.' }
        if ($answer -ne 'MAP_VISIBILITY_OK') { throw 'Raven map visibility acceptance not confirmed.' }
        $mapVisibilityAccepted = $true
        $logs = Get-FreshLogs
        $delivery = Test-RavenSnapshotDeliveryProofLines -BridgeLines @($logs.Bridge) -LoaderLines @($logs.Loader)
        if (-not $delivery.DeliveryReady) { throw 'Native delivery readiness disappeared during map visibility proof.' }
    }
    else {
        $answer = Read-Host 'Load advanced Raven save. Open map. Verify exact surviving Raven set, captions, realm filter, and immediate bottom-row text. Then on the SAME Raven without closing the map do Add -> Remove -> Add; verify the Raven is tracked again and NO boat/stock HUD marker appears. Type ADVANCED_OK, or REGRESSION if anything is wrong'
        if ($answer -eq 'REGRESSION') { throw 'Advanced-save or same-map Raven re-add manual regression reported.' }
        if ($answer -ne 'ADVANCED_OK') { throw 'Advanced-save/same-map re-add manual acceptance not confirmed.' }
        $sameMapReaddAccepted = $true
        $logs = Get-FreshLogs
        $delivery = Test-RavenSnapshotDeliveryProofLines -BridgeLines @($logs.Bridge) -LoaderLines @($logs.Loader)
        if (-not $delivery.DeliveryReady -or -not $delivery.AdvancedApplied) { throw 'Advanced-save Lua authority evidence missing.' }
    
        $answer = Read-Host 'Kill one loaded live Raven. Verify exact marker vanishes at once. Close/reopen map and verify it stays absent. NOW create a NEW MANUAL SAVE after the kill (do not rely on an autosave/checkpoint), then load that exact new save, reopen the map, and verify the same Raven is still absent. Type IMMEDIATE_OK only after loading that exact post-kill manual save, or REGRESSION if anything is wrong'
        if ($answer -eq 'REGRESSION') { throw 'Immediate-kill or checkpoint-reload manual regression reported.' }
        if ($answer -ne 'IMMEDIATE_OK') { throw 'Immediate-kill/checkpoint-reload manual acceptance not confirmed.' }
        $checkpointReloadAccepted = $true
        $logs = Get-FreshLogs
        $delivery = Test-RavenSnapshotDeliveryProofLines -BridgeLines @($logs.Bridge) -LoaderLines @($logs.Loader)
        if (-not $delivery.ImmediateEvent -or
            -not $delivery.CheckpointBoundaryObserved -or -not $delivery.PostBoundaryApplied -or
            -not $delivery.CheckpointBoundaryEpochMatched) {
            throw 'Gameplay Raven kill note or matching +1 post-kill save-load V2 authority evidence missing.'
        }
    
        $answer = Read-Host 'Now load a DIFFERENT pre-kill/older save where that same Raven is still alive. Open the map and verify that Raven comes back, while the newly loaded save otherwise shows its own Raven state. Type CROSSSAVE_OK, or REGRESSION if anything is wrong'
        if ($answer -eq 'REGRESSION') { throw 'Cross-save Raven revival/manual state isolation regression reported.' }
        if ($answer -ne 'CROSSSAVE_OK') { throw 'Cross-save Raven revival/manual state isolation acceptance not confirmed.' }
        $crossSaveRevivalAccepted = $true
    
        $answer = Read-Host 'Load true fresh save. Open map. Verify all 53 Ravens, captions, realm filter, and compass behavior. Type FRESH_OK, or REGRESSION if anything is wrong'
        if ($answer -eq 'REGRESSION') { throw 'Fresh-save manual regression reported.' }
        if ($answer -ne 'FRESH_OK') { throw 'Fresh-save manual acceptance not confirmed.' }
        $logs = Get-FreshLogs
        $delivery = Test-RavenSnapshotDeliveryProofLines -BridgeLines @($logs.Bridge) -LoaderLines @($logs.Loader)
        if (-not $delivery.FreshBoundaryObserved -or
            -not $delivery.FreshApplied -or
            -not $delivery.FreshBoundaryEpochMatched -or
            -not $delivery.Ordered) {
            throw 'Fresh 0-killed matching V2 boundary authority evidence missing.'
        }
    }

    while ($true) {
        $answer = Read-Host 'Quit GoW fully, then type FINALIZE'
        if ($answer -eq 'FINALIZE' -and @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -eq 0) { break }
        Write-Host 'GoW still open or token differs.'
    }
    $logs = Get-FreshLogs
    $delivery = Test-RavenSnapshotDeliveryProofLines -BridgeLines @($logs.Bridge) -LoaderLines @($logs.Loader)

    & $rollbackBridge -GameRoot $game
    $bridgeRolledBack = $true
    $bridgeInstalled = $false
    Restore-MapCandidate
    if (-not (Test-BridgeRollbackState) -or -not (Test-GameFileSnapshot $mapBefore)) { throw 'Combined rollback was not exact.' }

    if ($MapVisibilityOnly) {
        Publish-Proof 'RAVEN_MAP_VISIBILITY_LIVE_PROOF_PASSED' 'map_filters_and_mystic_gateway_fast_travel_visibility_proven' $delivery
        Write-Host 'RAVEN_MAP_VISIBILITY_LIVE_PROOF_PASSED'
    }
    else {
        Publish-Proof 'RAVEN_NATIVE_SNAPSHOT_DELIVERY_LIVE_PROOF_PASSED' 'advanced_immediate_reopen_checkpoint_reload_fresh_delivery_proven' $delivery
        Write-Host 'RAVEN_NATIVE_SNAPSHOT_DELIVERY_LIVE_PROOF_PASSED'
    }
    Write-Host "Evidence: $relativeDir"
}
catch {
    $outer = $_
    try { $outer.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'error.txt') -Encoding UTF8 } catch {}
    try { Get-FreshLogs | Out-Null } catch {}
    Write-Host "RAVEN_NATIVE_SNAPSHOT_DELIVERY_LIVE_PROOF_FAILED: $($outer.Exception.Message)"
    try { Stop-GoWProcesses } catch {}
    if ($bridgeInstalled -and -not $bridgeRolledBack) {
        try { & $rollbackBridge -GameRoot $game; $bridgeRolledBack = $true; $bridgeInstalled = $false } catch {
            $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'bridge-rollback-error.txt') -Encoding UTF8
        }
    }
    if ($mapInstalled -and -not $mapRolledBack) {
        try { Restore-MapCandidate } catch {
            $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $outDir 'map-rollback-error.txt') -Encoding UTF8
        }
    }
    try {
        $logs = Get-FreshLogs
        $delivery = Test-RavenSnapshotDeliveryProofLines -BridgeLines @($logs.Bridge) -LoaderLines @($logs.Loader)
        Publish-Proof 'RAVEN_NATIVE_SNAPSHOT_DELIVERY_LIVE_PROOF_FAILED' $outer.Exception.Message $delivery
    } catch { Write-Host "PROOF_PUSH_FAILED: $($_.Exception.Message)" }
    exit 1
}
finally {
    if ($bridgeInstalled -or $mapInstalled) {
        try { Stop-GoWProcesses } catch {}
        if ($bridgeInstalled -and -not $bridgeRolledBack) { try { & $rollbackBridge -GameRoot $game } catch {} }
        if ($mapInstalled -and -not $mapRolledBack) { try { Restore-MapCandidate } catch {} }
    }
    Stop-LocalTranscript
}
