param(
    [ValidateSet('Install','Rollback','Status')]
    [string]$Mode = 'Status',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$ConfirmRuntimeTest,
    [switch]$LibraryOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Reuse the hardened transaction engine only; no retired payload is installed.
$requestedMode = $Mode
$requestedGameRoot = $GameRoot
$requestedConfirm = [bool]$ConfirmRuntimeTest
$requestedLibrary = [bool]$LibraryOnly
$engine = Join-Path $PSScriptRoot 'nornir-runtime-candidate3.ps1'
$expectedEngineSha = '2be08999fbc529f3ac87f795cea33ac5d2bc16b62049480bd15de60a1be63add'
if ((Get-FileHash -LiteralPath $engine -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedEngineSha) {
    throw 'Pinned transaction engine changed.'
}
. $engine -LibraryOnly
$Mode = $requestedMode
$GameRoot = $requestedGameRoot
$ConfirmRuntimeTest = $requestedConfirm
$LibraryOnly = $requestedLibrary

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedBranch = 'codex/v104-raven-uid-compass-lifecycle-v3.2'
$stateRoot = Join-Path $repo 'build/v0.10.4-raven-uid-compass-lifecycle-v3.2/runtime/transaction'
$activeManifest = Join-Path $stateRoot 'active.json'
$candidateRoot = Join-Path $repo 'build/v0.10.4-raven-uid-compass-lifecycle-v3.2/offline/candidate/game-root'
$archivedReport = Join-Path $repo 'archive/field-logs/completionist-v104-raven-uid-compass-lifecycle-v3.2-offline.json'
$candidateLabel = 'raven-uid-compass-lifecycle-v3.2'
$builder = Join-Path $PSScriptRoot 'build-raven-uid-compass-lifecycle-v3.2.py'
$tests = Join-Path $PSScriptRoot 'test_raven_uid_compass_lifecycle_v32.py'
$luaTests = Join-Path $PSScriptRoot 'test_raven_uid_compass_lifecycle_v32_routing_lua.py'
$gameplayTests = Join-Path $PSScriptRoot 'test_raven_uid_compass_lifecycle_v32_events.py'

$files = [ordered]@{
    'mapmaster.dcb' = 'exec/dc/pc_le/mapmaster.dcb'
    'mapcoords.dcb' = 'exec/dc/pc_le/mapcoords.dcb'
    'wad_r_ui.dcb' = 'exec/dc/pc_le/wad_r_ui.dcb'
    'mapmenu.lua' = 'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
    'precisionchallenge.lua' = 'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua'
}

$frozenRavenShas = [ordered]@{
    'mapmaster.dcb' = 'b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f'
    'mapcoords.dcb' = '945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb'
    'wad_r_ui.dcb' = '765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d'
    'mapmenu.lua' = '67d069a798417b631c271f48c129fb2083591b81a31859ab94769fbbb8b01c6b'
    'precisionchallenge.lua' = 'c22aa8a649e2380a60040d64c3843a392101fb6dcd733f9078d24141600ad69c'
}

$sharedLoaderBinaryShas = [ordered]@{
    'mapmaster.dcb' = '1e1d5086815bc8553490bff915fea210a8be4f80ce6c88b418b62d7050690a31'
    'mapcoords.dcb' = '36bd16f8f21c6387b556e156055ea02f5c262b30a6c450cc0efa05734efb1a0c'
    'wad_r_ui.dcb' = '9a434a29ed2e333362e60ac7f224d26855fc9dc86834aa94504a170854e22f2b'
}

# Pin every source file that can affect this candidate. These are Git blob IDs, not
# runtime resource IDs; they are used only to make the local offline build reproducible.
$sourceBlobPins = [ordered]@{
    '.gitattributes' = 'af1804dfefb8ba78fe7bd083b4fa4e59b7c496d1'
    'tools/v0.10.4/raven-uid-compass-routing-v3.2.lua' = 'bca3f74be44c6e5e1accdb9656835a89456a8618'
    'tools/v0.10.4/raven-shared-loader-twin.lua' = '7e20dc7f6c5120760bd9928eebb4bdd97ff53425'
    'tools/v0.10.4/raven-uid-compass-lifecycle-v3.1-events.lua' = '18e2b1a64e245d79c4eac025abb2ffc9fffcf6d3'
    'tools/v0.10.4/raven-uid-compass-lifecycle-v3.2-events.lua' = '18e2b1a64e245d79c4eac025abb2ffc9fffcf6d3'
    'tools/v0.10.4/build-raven-uid-compass-lifecycle-v3.2.py' = '9f33ff1f97de9519b1b82a3f9cf1dffed192d1ec'
    'tools/v0.10.4/build-raven-shared-loader.py' = '9a59bf573a9773923282f0f9bbb9f842487b67b2'
    'tools/v0.10.4/build-raven-twin-stage-a-offline.py' = '861d5f1f2a867044e6b9b6cca844fb124ec17ee6'
    'tools/v0.10.3/inspect-native-markers.py' = '12a1876c56a64be2b7cc1482de62f4e37b0e863e'
    'tools/v0.10.4/verify-raven-production-state.py' = 'a2b848c87756cba650c1967e0fcf78443737ed42'
    'tools/v0.10.4/test_raven_uid_compass_lifecycle_v32.py' = '3bb07d09cc9cc0a00bd865ab88601d091fef69fb'
    'tools/v0.10.4/test_raven_uid_compass_lifecycle_v32_routing_lua.py' = 'c6f4ae60166e65b6e054d2b9fc9fe97fb4ce9dce'
    'tools/v0.10.4/test_raven_uid_compass_lifecycle_v32_events.py' = '46d669f6c27ec6341b16422a0ed0f403470f41a4'
    'tools/v0.10.4/test_raven_shared_loader_lua.py' = '159f154e799599acec3cc1c6b5ff70c49148c150'
    'tools/v0.10.4/nornir-runtime-candidate3.ps1' = 'e66705836f9c0c5578377572d629929b5b330119'
    'tools/v0.10.4/test-raven-uid-compass-lifecycle-v3.2-transaction.ps1' = '0fc06d4b4a2ee7d2787ccfaa5b3f50c0500045f3'
    'tools/v0.10.4/verify-raven-uid-compass-lifecycle-v3.2.ps1' = '7ef56fe17a41b8c68d0de001752327702ecce096'
}

$candidateShaPins = [ordered]@{
    'mapmaster.dcb' = '1e1d5086815bc8553490bff915fea210a8be4f80ce6c88b418b62d7050690a31'
    'mapcoords.dcb' = '36bd16f8f21c6387b556e156055ea02f5c262b30a6c450cc0efa05734efb1a0c'
    'wad_r_ui.dcb' = '9a434a29ed2e333362e60ac7f224d26855fc9dc86834aa94504a170854e22f2b'
    'mapmenu.lua' = '99dd919925196833c985a22ee1caef21c776bc91ec9ec462b4d128c39ce6a01e'
    'precisionchallenge.lua' = '61e6bc8efe1fcb9b2a6e796aa86ce9a5f74fc18e97229aae7cc52b652a565800'
}

function Assert-SourceBlobPins {
    foreach ($path in $sourceBlobPins.Keys) {
        $working = (& git -C $repo hash-object -- $path).Trim().ToLowerInvariant()
        if ($LASTEXITCODE -ne 0 -or $working -ne [string]$sourceBlobPins[$path]) {
            throw "Pinned working source blob differs: $path"
        }
        $actual = (& git -C $repo rev-parse ("HEAD:" + $path)).Trim().ToLowerInvariant()
        if ($LASTEXITCODE -ne 0 -or $actual -ne [string]$sourceBlobPins[$path]) {
            throw "Pinned source blob differs: $path ($actual)"
        }
    }
}

function Assert-FrozenRavenMapFiles([string]$Game) {
    foreach ($name in $files.Keys) {
        $path = Resolve-SafeChildPath -Root $Game -Relative ([string]$files[$name]) -Label 'frozen Raven'
        if ((Get-Sha256 $path) -ne [string]$frozenRavenShas[$name]) {
            throw "Frozen Raven SHA differs: $name"
        }
    }
}

function Invoke-FrozenRavenVerifier([string]$Game) {
    $verifier = Join-Path $PSScriptRoot 'verify-raven-production-state.py'
    $output = Join-Path $repo 'build/v0.10.4-raven-uid-compass-lifecycle-v3.2/runtime/frozen-raven-verification.json'
    & py.exe -3 $verifier --game-root $Game --repo-root $repo --output $output | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verifier failed.' }
}

function Invoke-OfflineBuildAndTests([string]$Game) {
    Assert-SourceBlobPins
    Assert-FrozenRavenMapFiles -Game $Game

    & py.exe -3 $builder --raven-root $Game | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'UID-lifecycle v3.2 offline build failed.' }

    $oldRoot = $env:COMPLETIONIST_RAVEN_ROOT
    try {
        $env:COMPLETIONIST_RAVEN_ROOT = $Game
        & py.exe -3 $tests | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'UID-lifecycle v3.2 offline tests failed.' }
        & py.exe -3 $gameplayTests | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Gameplay lifecycle regression failed.' }
        & py.exe -3 (Join-Path $PSScriptRoot 'test_raven_shared_loader_lua.py') | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Twin lifecycle regression failed.' }
        & py.exe -3 $luaTests | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'UID-lifecycle v3.2 Lua 5.1 regression failed.' }
    }
    finally {
        if ($null -eq $oldRoot) { Remove-Item Env:COMPLETIONIST_RAVEN_ROOT -ErrorAction SilentlyContinue }
        else { $env:COMPLETIONIST_RAVEN_ROOT = $oldRoot }
    }

    & py.exe -3 $builder --raven-root $Game --check | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'UID-lifecycle v3.2 deterministic rebuild check failed.' }
}

function Assert-UidRoutingProof {
    if (-not (Test-Path -LiteralPath $archivedReport -PathType Leaf)) { throw 'UID-lifecycle v3.2 offline proof missing.' }
    $proof = Get-Content -LiteralPath $archivedReport -Raw | ConvertFrom-Json
    if ($proof.schema -ne 5 -or
        $proof.result -ne 'RAVEN_UID_COMPASS_LIFECYCLE_V32_OFFLINE_PROOF_PASSED' -or
        $proof.branch_contract -ne $expectedBranch -or
        $proof.base_head -ne '4b028127e3a196742d0073d8c8fb339e2098f5f6' -or
        $proof.shared_loader_runtime_success_head -ne 'e29b841b2e8799ebe90780413c8330755415183f' -or
        $proof.ready_for_runtime_test -ne $true -or
        $proof.runtime_test_performed -ne $false -or
        $proof.game_files_written -ne $false -or
        $proof.retired_candidates_used -ne $false -or
        $proof.progression_or_marker_state_writes -ne $false -or
        $proof.map_title_behavior_changed -ne $false) {
        throw 'UID-lifecycle v3.2 offline proof gate differs.'
    }

    if ($proof.identities.raven_uid -ne 'E15E6BC82AE2773E' -or
        $proof.identities.twin_uid -ne '2F530E7F3F156D90' -or
        $proof.identities.shared_map_loader -ne 'goMapIconCompletionistRaven' -or
        $proof.identities.shared_map_resource_hash -ne '584F31DC8BD6E738' -or
        $proof.identities.compass_class -ne 'CompletionistRaven') {
        throw 'UID-lifecycle v3.2 identity contract differs.'
    }

    if ($proof.routing_contract.selection_identity_source -ne 'MapOn.MapCollisionChangeHandler exact collision table object reference' -or
        $null -ne $proof.routing_contract.selection_fallback -or
        ($proof.routing_contract.selection_state_machine -join ',') -ne 'none,candidate-custom,armed-custom' -or
        $null -ne $proof.routing_contract.selection_frame_ttl -or
        $proof.routing_contract.selection_armed_one_shot -ne $true -or
        $proof.routing_contract.selection_arm_signal -ne 'GetShowOnCompassPrompt visible with completionistMapV100Selected=true and currMarkerID=nil' -or
        $proof.routing_contract.confirmed_stock_signal -ne 'visible GetShowOnCompassPrompt with currMarkerID set; action guard repeats currMarkerID check' -or
        $proof.routing_contract.incidental_noncustom_collision_policy -ne 'ignore callback alone; defer to prompt owner or prompt availability' -or
        ($proof.routing_contract.selection_disarm -join ',') -ne 'different custom collision replaces identity,visible native stock prompt with currMarkerID,visible non-Raven custom prompt,prompt unavailable,MapOn.SubmenuExit,MapOn.Exit,MapOn.ClearIcons,armed action consumption,action without prompt arm,custom prompt owner lost before action,real Raven completion' -or
        $proof.routing_contract.native_identity_source -ne 'game.Map.GetMarkerInfo(Name).Id' -or
        $proof.routing_contract.same_visual_resource_for_both_map_markers -ne $true -or
        $proof.routing_contract.selected_name_routed_to_native_compass -ne $true -or
        $proof.routing_contract.selected_uid_used_for_active_target_comparison -ne $true -or
        $proof.routing_contract.single_active_custom_target_policy -ne $true -or
        $proof.routing_contract.replacement_hide_failure_policy -ne 'refuse replacement; never broaden hide scope' -or
        $proof.routing_contract.new_wad_resource_identity -ne $false -or
        $proof.routing_contract.compassgraph_changed -ne $false -or
        $proof.routing_contract.gameplay_hook -ne 'precisionchallenge.OnHitByWeapon post-native ravenKilled' -or
        $proof.routing_contract.gameplay_hook_byte_identical_to_v31 -ne $true -or
        $proof.routing_contract.gameplay_cleanup_owner -ne 'persistent precisionchallenge Raven lifecycle' -or
        $proof.routing_contract.gameplay_mapmenu_dependency -ne $false -or
        $proof.routing_contract.gameplay_target_match -ne 'CompletionistRaven enumeration plus exact real marker Id' -or
        $proof.routing_contract.completion_latch_reversible -ne $true -or
        $proof.routing_contract.polling -ne $false -or
        $proof.routing_contract.event_retry -ne 'level.timer.StartLevelTimer: 0.1 seconds, at most 20, ticket cancelled by false restore/start' -or
        $proof.routing_contract.event_retry_schedule_failure_safe -ne $true -or
        $proof.routing_contract.production_destroy_recycles_twin -ne $false -or
        ($proof.routing_contract.rearm_hooks -join ',') -ne 'OnRestoreCheckpoint,OnStart' -or
        ($proof.routing_contract.twin_cleanup_hooks -join ',') -ne 'MapOn.SubmenuExit,MapOn.Exit,MapOn.ClearIcons' -or
        $proof.routing_contract.lifecycle_observation -ne $true -or
        $proof.routing_contract.completion_oracle -ne 'native precisionchallenge ravenKilled after native callback' -or
        $proof.routing_contract.completion_cleanup_scope -ne 'exact real Raven CompletionistRaven target only' -or
        $proof.routing_contract.twin_lifetime_independent_of_original_ui_object -ne $true -or
        $proof.routing_contract.lifecycle_progression_mutation -ne $false -or
        $proof.routing_contract.synthetic_progression_writes -ne $false) {
        throw 'UID-lifecycle v3.2 behavior contract differs.'
    }

    $expected = @($files.Values | Sort-Object)
    $actual = @($proof.files.PSObject.Properties.Name | Sort-Object)
    if (($expected -join "`n") -ne ($actual -join "`n")) { throw 'UID-lifecycle v3.2 proof file set differs.' }

    foreach ($name in $files.Keys) {
        $relative = [string]$files[$name]
        if ($proof.source_sha256.PSObject.Properties[$relative].Value -ne $frozenRavenShas[$name]) {
            throw "UID-lifecycle v3.2 frozen source SHA differs in proof: $name"
        }
        if ($sharedLoaderBinaryShas.Contains($name) -and
            $proof.files.PSObject.Properties[$relative].Value.sha256 -ne $sharedLoaderBinaryShas[$name]) {
            throw "UID-lifecycle v3.2 binary is not the proven shared-loader candidate: $name"
        }
    }
    return $proof
}

function Get-CandidateShasFromProof([object]$Proof) {
    $result = [ordered]@{}
    foreach ($name in $files.Keys) {
        $relative = [string]$files[$name]
        $sha = [string]$Proof.files.PSObject.Properties[$relative].Value.sha256
        if ($sha -notmatch '^[0-9a-f]{64}$') { throw "Invalid candidate SHA in proof: $name" }
        if ($sha -ne [string]$candidateShaPins[$name]) { throw "Pinned candidate SHA differs: $name" }
        $result[$name] = $sha
    }
    return $result
}

function Assert-UidRoutingCandidate([object]$Proof, [System.Collections.IDictionary]$CandidateShas) {
    if (-not (Test-Path -LiteralPath $candidateRoot -PathType Container)) { throw 'UID-lifecycle v3.2 candidate missing.' }
    $actual = @(Get-ChildItem -LiteralPath $candidateRoot -Recurse -File | ForEach-Object {
        Get-SafeRelativePath -Root $candidateRoot -Path $_.FullName -Label 'UID-lifecycle v3.2 candidate'
    } | Sort-Object)
    $expected = @($files.Values | Sort-Object)
    if (($actual -join "`n") -ne ($expected -join "`n")) { throw 'UID-lifecycle v3.2 candidate must contain exactly five approved files.' }

    foreach ($name in $files.Keys) {
        $path = Resolve-SafeChildPath -Root $candidateRoot -Relative ([string]$files[$name]) -Label 'UID-lifecycle v3.2 candidate'
        if ((Get-Sha256 $path) -ne [string]$CandidateShas[$name]) { throw "UID-lifecycle v3.2 candidate SHA differs: $name" }
    }
}

function Get-UidRoutingRollbackCheckInstalled([string]$Status) {
    if ($Status -eq 'installed') { return $true }
    if ($Status -in @('backup-complete','installing','rolling-back',
        'rolling-back-after-install-failure','rollback-failed-after-install-failure')) { return $false }
    throw "Transaction state cannot roll back: $Status"
}

if ($LibraryOnly) { return }

if ($Mode -eq 'Status') {
    Write-Host 'RAVEN_UID_COMPASS_LIFECYCLE_V32_RUNTIME_STATUS'
    Write-Host "  branch: $expectedBranch"
    Write-Host "  offline proof present: $(Test-Path -LiteralPath $archivedReport -PathType Leaf)"
    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) {
        Write-Host '  active transaction: none'
        exit 0
    }
    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host "  status: $($manifest.status)"
    Write-Host '  runtime proof: human observation + loader log required'
    exit 0
}

if ($Mode -eq 'Install' -and -not $ConfirmRuntimeTest) {
    throw 'Install disarmed. Manual runtime test needs -ConfirmRuntimeTest.'
}

Assert-PathTopology -Game $GameRoot -Candidate $candidateRoot -State $stateRoot
Assert-GameRootIdentity -Game $GameRoot
$branch = Assert-Branch
Assert-TrackedTreeClean
Assert-SourceBlobPins
Assert-GameClosed -Game $GameRoot
$operationHead = Get-RepoHead
$writeGuard = {
    [void](Assert-Branch)
    Assert-TrackedTreeClean
    Assert-SourceBlobPins
    Assert-GameClosed -Game $GameRoot
    Assert-RepoHead -ExpectedHead $operationHead
}

if ($Mode -eq 'Install') {
    if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
        $existingProof = if (Test-Path -LiteralPath $archivedReport -PathType Leaf) { Assert-UidRoutingProof } else { $null }
        if ($null -ne $existingProof) {
            $existingShas = Get-CandidateShasFromProof -Proof $existingProof
            $old = Get-ValidatedActiveTransaction -Active $activeManifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -ProofPath $archivedReport -FileMap $files -CandidateShas $existingShas -CandidateLabel $candidateLabel -RepoBranch $branch
            if ($old.status -notin @('rolled-back','rolled-back-after-install-failure')) { throw 'Active UID-lifecycle v3.2 transaction exists.' }
        }
    }

    Assert-FrozenRavenMapFiles -Game $GameRoot
    Invoke-FrozenRavenVerifier -Game $GameRoot
    Invoke-OfflineBuildAndTests -Game $GameRoot
    $proof = Assert-UidRoutingProof
    $candidateShas = Get-CandidateShasFromProof -Proof $proof
    Assert-UidRoutingCandidate -Proof $proof -CandidateShas $candidateShas

    $preWriteValidation = {
        & $writeGuard
        Assert-FrozenRavenMapFiles -Game $GameRoot
        Invoke-FrozenRavenVerifier -Game $GameRoot
        Assert-UidRoutingCandidate -Proof $proof -CandidateShas $candidateShas
        Assert-GameClosed -Game $GameRoot
    }

    $manifest = Invoke-TransactionalInstall -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -FileMap $files -CandidateShas $candidateShas -CandidateLabel $candidateLabel -RepoBranch $branch -RepoHead $operationHead -ProofPath $archivedReport -PreWriteValidation $preWriteValidation -WriteGuard $writeGuard
    Write-Host 'RAVEN_UID_COMPASS_LIFECYCLE_V32_INSTALLED_FOR_HUMAN_TEST'
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host '  game launched: false'
    Write-Host '  binary candidate: exact proven shared-loader bytes'
    Write-Host '  additional changes: collision-event UID routing + gameplay-side exact real cleanup + independent Twin lifetime'
    Write-Host '  progression/marker-state writes: false'
    exit 0
}

if ($Mode -eq 'Rollback') {
    $proof = Assert-UidRoutingProof
    $candidateShas = Get-CandidateShasFromProof -Proof $proof
    Assert-UidRoutingCandidate -Proof $proof -CandidateShas $candidateShas
    $manifest = Get-ValidatedActiveTransaction -Active $activeManifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -ProofPath $archivedReport -FileMap $files -CandidateShas $candidateShas -CandidateLabel $candidateLabel -RepoBranch $branch
    $checkInstalled = Get-UidRoutingRollbackCheckInstalled -Status ([string]$manifest.status)
    Restore-State -Manifest $manifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -ProofPath $archivedReport -FileMap $files -CandidateShas $candidateShas -CandidateLabel $candidateLabel -RepoBranch $branch -CheckInstalled $checkInstalled -Force $false -WriteGuard $writeGuard
    $manifest.status = 'rolled-back'
    $manifest.rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
    Save-TransactionManifest -Manifest $manifest -Active $activeManifest
    Assert-FrozenRavenMapFiles -Game $GameRoot
    Invoke-FrozenRavenVerifier -Game $GameRoot
    Write-Host 'RAVEN_UID_COMPASS_LIFECYCLE_V32_ROLLED_BACK'
    Write-Host '  exact pre-install bytes restored: true'
    exit 0
}
