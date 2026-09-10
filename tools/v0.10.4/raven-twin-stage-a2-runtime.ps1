param(
    [ValidateSet('Install','Rollback','Status')]
    [string]$Mode = 'Status',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$ConfirmRuntimeTest,
    [switch]$LibraryOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Reuse the hardened transaction primitives committed at 036628c. Stage A2
# changes only the Raven Twin r_ui.wad type accounting and keeps the approved
# runtime surface to the same four map-only files.
$requestedMode = $Mode
$requestedGameRoot = $GameRoot
$requestedConfirmRuntimeTest = [bool]$ConfirmRuntimeTest
$requestedLibraryOnly = [bool]$LibraryOnly
$engine = Join-Path $PSScriptRoot 'nornir-runtime-candidate3.ps1'
if (-not (Test-Path -LiteralPath $engine -PathType Leaf)) { throw "Missing hardened transaction engine: $engine" }
$expectedEngineSha = '2be08999fbc529f3ac87f795cea33ac5d2bc16b62049480bd15de60a1be63add'
$engineSha = (Get-FileHash -LiteralPath $engine -Algorithm SHA256).Hash.ToLowerInvariant()
if ($engineSha -ne $expectedEngineSha) {
    throw "Hardened 036628c transaction engine changed: $engineSha"
}
. $engine -LibraryOnly
$Mode = $requestedMode
$GameRoot = $requestedGameRoot
$ConfirmRuntimeTest = $requestedConfirmRuntimeTest
$LibraryOnly = $requestedLibraryOnly

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedBranch = 'fix/v104-raven-twin-type-accounting'
$stateRoot = Join-Path $repo 'build\v0.10.4-raven-twin-stage-a2\runtime\transaction'
$activeManifest = Join-Path $stateRoot 'active.json'
$candidateRoot = Join-Path $repo 'build\v0.10.4-raven-twin-stage-a2\offline\candidate\game-root'
$archivedReport = Join-Path $repo 'archive\field-logs\completionist-v104-raven-twin-stage-a2-offline.json'
$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$candidateLabel = 'raven-twin-stage-a2'

$files = [ordered]@{
    'r_ui.wad' = 'exec/wad/pc_le/r_ui.wad'
    'wad_r_ui.dcb' = 'exec/dc/pc_le/wad_r_ui.dcb'
    'mapmaster.dcb' = 'exec/dc/pc_le/mapmaster.dcb'
    'mapcoords.dcb' = 'exec/dc/pc_le/mapcoords.dcb'
}
$frozenRavenShas = [ordered]@{
    'r_ui.wad' = '5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60'
    'wad_r_ui.dcb' = '765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d'
    'mapmaster.dcb' = 'b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f'
    'mapcoords.dcb' = '945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb'
}
$approvedCandidateShas = [ordered]@{
    'r_ui.wad' = '4578112255a95e1d7014d3b42538531093c4e8e1f2ef4933e66b94aab1721d19'
    'wad_r_ui.dcb' = 'f0f67e7797456c17d2d8c1671c5998668cf48d1ad3a30d15c540363b4df756ae'
    'mapmaster.dcb' = '2acc035529b7078e73957668e987df24775d464a41fc32f9a0622f26786011bf'
    'mapcoords.dcb' = '36bd16f8f21c6387b556e156055ea02f5c262b30a6c450cc0efa05734efb1a0c'
}

function Assert-StageA2Proof {
    if (-not (Test-Path -LiteralPath $archivedReport -PathType Leaf)) { throw "Stage A2 proof missing: $archivedReport" }
    $proof = Get-Content -LiteralPath $archivedReport -Raw | ConvertFrom-Json
    if ([string]$proof.result -ne 'RAVEN_TWIN_STAGE_A2_TYPE_ACCOUNTING_OFFLINE_PROOF_PASSED') {
        throw 'Unexpected Stage A2 proof result.'
    }
    if ($proof.ready_for_runtime_test -ne $true -or $proof.runtime_test_performed -ne $false) {
        throw 'Stage A2 proof is not at the offline-ready gate.'
    }
    if ([string]$proof.stage.scope -ne 'map-only Raven Twin with Raven artwork') {
        throw 'Stage A2 scope changed.'
    }
    if ($proof.stage.compass_inworld_added -or $proof.stage.lifecycle_added -or $proof.stage.nornir_art_added) {
        throw 'Stage A2 proof contains a forbidden later stage.'
    }
    if (-not $proof.proofs.exact_normalization_to_frozen_raven_for_all_four_files -or
        -not $proof.proofs.original_raven_records_byte_identical -or
        -not $proof.proofs.stock_dock_boatdock_records_byte_identical -or
        -not $proof.proofs.all_twin_differences_classified -or
        [int]$proof.proofs.unexplained_changed_payload_bytes -ne 0) {
        throw 'Stage A2 byte-preservation or classification proof failed.'
    }
    if ($proof.source.candidate_1_used -or $proof.source.candidate_2_used -or
        $proof.source.candidate_3_used -or $proof.source.old_nornir_lifecycle_artifacts_used) {
        throw 'Stage A2 proof used a retired Nornir construction donor.'
    }
    if ($proof.safety.installed_game_files_written -or $proof.safety.god_of_war_launched -or
        $proof.safety.save_files_written -or $proof.safety.progression_state_written -or
        $proof.safety.marker_state_written -or $proof.safety.runtime_installer_executed) {
        throw 'Stage A2 offline safety proof is not clean.'
    }

    $accounting = $proof.proofs.r_ui_wad.accounting
    if ([int]$accounting.before_total -ne 16805 -or
        [int]$accounting.after_total -ne 16811 -or
        [int]$accounting.physical_payload_delta -ne 8 -or
        [int]$accounting.typed_payload_delta -ne 6 -or
        [int]$accounting.untyped_gpu_payload_delta -ne 2 -or
        [int]$accounting.accounted_delta -ne 6 -or
        [string]$accounting.accounting_basis -ne 'serialized resource type signatures, never physical payload index ranges') {
        throw 'Stage A2 serialized-type accounting proof changed.'
    }
    $increments = $accounting.type_increments
    if ([int]$increments.'0xA' -ne 1 -or
        [int]$increments.'0x10001' -ne 1 -or
        [int]$increments.'0x20001' -ne 1 -or
        [int]$increments.'0x2000C' -ne 1 -or
        [int]$increments.'0x10015' -ne 2) {
        throw 'Stage A2 type-row increments changed.'
    }

    $properties = @($proof.files.PSObject.Properties)
    if ($properties.Count -ne @($files.Keys).Count) { throw 'Stage A2 proof must contain exactly four files.' }
    $expectedPaths = @($files.Values | ForEach-Object { ([string]$_).Replace('\','/') } | Sort-Object)
    $actualPaths = @($properties.Name | ForEach-Object { ([string]$_).Replace('\','/') } | Sort-Object)
    if (($expectedPaths -join "`n") -ne ($actualPaths -join "`n")) { throw 'Stage A2 proof file set changed.' }
    foreach ($name in $files.Keys) {
        $relative = ([string]$files[$name]).Replace('\','/')
        $entry = $proof.files.PSObject.Properties[$relative]
        if ($null -eq $entry -or ([string]$entry.Value.sha256).ToLowerInvariant() -ne $approvedCandidateShas[$name]) {
            throw "Stage A2 proof SHA changed: $name"
        }
    }
    return $proof
}

function Assert-StageA2Candidate {
    [void](Assert-StageA2Proof)
    if (-not (Test-Path -LiteralPath $candidateRoot -PathType Container)) { throw "Stage A2 candidate missing: $candidateRoot" }
    $diskFiles = @(Get-ChildItem -LiteralPath $candidateRoot -Recurse -File | ForEach-Object {
        Get-SafeRelativePath -Root $candidateRoot -Path $_.FullName -Label 'Stage A2 candidate file'
    } | Sort-Object)
    $expected = @($files.Values | ForEach-Object { ([string]$_).Replace('\','/') } | Sort-Object)
    if (($diskFiles -join "`n") -ne ($expected -join "`n")) { throw 'Stage A2 candidate must contain exactly the approved four files.' }
    foreach ($name in $files.Keys) {
        $source = Resolve-SafeChildPath -Root $candidateRoot -Relative ([string]$files[$name]) -Label 'Stage A2 candidate source'
        if ((Get-Sha256 $source) -ne $approvedCandidateShas[$name]) { throw "Stage A2 candidate SHA mismatch: $name" }
    }
}

function Assert-FrozenRavenMapFiles([string]$Game) {
    foreach ($name in $files.Keys) {
        $path = Resolve-SafeChildPath -Root $Game -Relative ([string]$files[$name]) -Label 'frozen Raven map file'
        if ((Get-Sha256 $path) -ne $frozenRavenShas[$name]) { throw "Frozen Raven map file changed: $name" }
    }
}

function Invoke-RavenVerifier([string]$Game) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $Game -ExpectedBranch $expectedBranch | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verification failed.' }
}

function Get-StageA2RollbackCheckInstalled([string]$Status) {
    if ($Status -eq 'installed') { return $true }
    if ($Status -in @(
        'backup-complete', 'installing', 'rolling-back',
        'rolling-back-after-install-failure', 'rollback-failed-after-install-failure'
    )) {
        return $false
    }
    throw "Stage A2 transaction status '$Status' cannot be rolled back."
}

if ($LibraryOnly) { return }

if ($Mode -eq 'Status') {
    Write-Host 'RAVEN_TWIN_STAGE_A2_RUNTIME_STATUS'
    Write-Host "  offline proof: $archivedReport"
    Write-Host '  runtime proof: not performed'
    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) {
        Write-Host '  active transaction: none'
        exit 0
    }
    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host "  status: $($manifest.status)"
    Write-Host "  files: $(@($manifest.entries).Count)"
    exit 0
}

if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }
Assert-PathTopology -Game $GameRoot -Candidate $candidateRoot -State $stateRoot
Assert-GameRootIdentity -Game $GameRoot
$branch = Assert-Branch
if ($branch -ne $expectedBranch) { throw "Expected Git branch '$expectedBranch', found '$branch'." }
Assert-TrackedTreeClean
Assert-GameClosed -Game $GameRoot
$operationHead = Get-RepoHead

if ($Mode -eq 'Install') {
    if (-not $ConfirmRuntimeTest) {
        throw 'Stage A2 install is disarmed. Use -ConfirmRuntimeTest only for the approved human map-open test.'
    }
    Assert-StageA2Candidate
    if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
        $old = Get-ValidatedActiveTransaction -Active $activeManifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -ProofPath $archivedReport -FileMap $files -CandidateShas $approvedCandidateShas -CandidateLabel $candidateLabel -RepoBranch $branch
        if ([string]$old.status -notin @('rolled-back','rolled-back-after-install-failure')) { throw "Active Stage A2 transaction exists with status '$($old.status)'." }
    }

    Assert-FrozenRavenMapFiles -Game $GameRoot
    Invoke-RavenVerifier -Game $GameRoot

    $preWriteValidation = {
        $currentBranch = Assert-Branch
        if ($currentBranch -ne $expectedBranch) { throw "Expected Git branch '$expectedBranch', found '$currentBranch'." }
        Assert-RepoHead -ExpectedHead $operationHead
        Assert-TrackedTreeClean
        Assert-GameClosed -Game $GameRoot
        Assert-FrozenRavenMapFiles -Game $GameRoot
        Invoke-RavenVerifier -Game $GameRoot
        Assert-GameClosed -Game $GameRoot
    }
    $writeGuard = {
        Assert-GameClosed -Game $GameRoot
        Assert-RepoHead -ExpectedHead $operationHead
        Assert-TrackedTreeClean
    }
    $manifest = Invoke-TransactionalInstall -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -FileMap $files -CandidateShas $approvedCandidateShas -CandidateLabel $candidateLabel -RepoBranch $branch -RepoHead $operationHead -ProofPath $archivedReport -PreWriteValidation $preWriteValidation -WriteGuard $writeGuard

    Write-Host 'RAVEN_TWIN_STAGE_A2_INSTALLED_FOR_HUMAN_RUNTIME_TEST'
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host '  files installed: 4 map-only files'
    Write-Host "  corrected r_ui.wad: $($approvedCandidateShas['r_ui.wad'])"
    Write-Host '  typed accounting: 16805 -> 16811 (+6 typed, +8 physical)'
    Write-Host '  game launched by installer: false'
    Write-Host '  saves/progression/marker state written: false'
    Write-Host "  manifest: $(Join-Path ([string]$manifest.transaction_root) 'manifest.json')"
    exit 0
}

if ($Mode -eq 'Rollback') {
    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) { throw 'No Stage A2 transaction exists.' }
    [void](Assert-StageA2Proof)
    $manifest = Get-ValidatedActiveTransaction -Active $activeManifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -ProofPath $archivedReport -FileMap $files -CandidateShas $approvedCandidateShas -CandidateLabel $candidateLabel -RepoBranch $branch
    $checkInstalled = Get-StageA2RollbackCheckInstalled -Status ([string]$manifest.status)
    $writeGuard = {
        Assert-GameClosed -Game $GameRoot
        Assert-RepoHead -ExpectedHead $operationHead
        Assert-TrackedTreeClean
    }
    Restore-State -Manifest $manifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -ProofPath $archivedReport -FileMap $files -CandidateShas $approvedCandidateShas -CandidateLabel $candidateLabel -RepoBranch $branch -CheckInstalled $checkInstalled -Force $false -WriteGuard $writeGuard
    $manifest.status = 'rolled-back'
    $manifest.rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
    Save-TransactionManifest -Manifest $manifest -Active $activeManifest
    Assert-FrozenRavenMapFiles -Game $GameRoot
    Invoke-RavenVerifier -Game $GameRoot
    Write-Host 'RAVEN_TWIN_STAGE_A2_ROLLED_BACK'
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host '  exact pre-install state restored: true'
    Write-Host '  Raven production verifier passed: true'
    exit 0
}
