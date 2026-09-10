param(
    [ValidateSet('Install','Rollback','Status')]
    [string]$Mode = 'Status',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$ConfirmRuntimeTest,
    [switch]$LibraryOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Reuse the hardened transaction primitives committed at 036628c. The Stage A
# wrapper narrows the approved set to four map-only files and never enables the
# legacy force-rollback path.
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
$expectedBranch = 'codex/v104-raven-production'
$stateRoot = Join-Path $repo 'build\v0.10.4-raven-twin-stage-a\runtime\transaction'
$activeManifest = Join-Path $stateRoot 'active.json'
$candidateRoot = Join-Path $repo 'build\v0.10.4-raven-twin-stage-a\offline\candidate\game-root'
$archivedReport = Join-Path $repo 'archive\field-logs\completionist-v104-raven-twin-stage-a-offline.json'
$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$candidateLabel = 'raven-twin-stage-a'

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
    'r_ui.wad' = '86ba2b6a96d869c25f825e5cd64aebae10649d5904f93b5723d53359ed24d0a5'
    'wad_r_ui.dcb' = 'f0f67e7797456c17d2d8c1671c5998668cf48d1ad3a30d15c540363b4df756ae'
    'mapmaster.dcb' = '2acc035529b7078e73957668e987df24775d464a41fc32f9a0622f26786011bf'
    'mapcoords.dcb' = '36bd16f8f21c6387b556e156055ea02f5c262b30a6c450cc0efa05734efb1a0c'
}

function Assert-StageAProof {
    if (-not (Test-Path -LiteralPath $archivedReport -PathType Leaf)) { throw "Stage A proof missing: $archivedReport" }
    $proof = Get-Content -LiteralPath $archivedReport -Raw | ConvertFrom-Json
    if ([string]$proof.result -ne 'RAVEN_TWIN_STAGE_A_OFFLINE_PROOF_PASSED') { throw 'Unexpected Stage A proof result.' }
    if ([string]$proof.branch_contract -ne $expectedBranch) { throw 'Stage A proof branch contract changed.' }
    if ($proof.ready_for_runtime_test -ne $true -or $proof.runtime_test_performed -ne $false) { throw 'Stage A proof is not at the offline-ready gate.' }
    if ($proof.stage.scope -ne 'map-only Raven Twin with Raven artwork') { throw 'Stage A scope changed.' }
    if ($proof.stage.compass_inworld_added -or $proof.stage.lifecycle_added -or $proof.stage.nornir_art_added) { throw 'Stage A proof contains a forbidden later stage.' }
    if (-not $proof.proofs.exact_normalization_to_frozen_raven_for_all_four_files -or
        -not $proof.proofs.original_raven_records_byte_identical -or
        -not $proof.proofs.stock_dock_boatdock_records_byte_identical -or
        -not $proof.proofs.all_twin_differences_classified -or
        [int]$proof.proofs.unexplained_changed_payload_bytes -ne 0) {
        throw 'Stage A byte-preservation or classification proof failed.'
    }
    if ($proof.source.candidate_1_used -or $proof.source.candidate_2_used -or
        $proof.source.candidate_3_used -or $proof.source.old_nornir_lifecycle_artifacts_used) {
        throw 'Stage A proof used a retired Nornir construction donor.'
    }
    if ($proof.safety.installed_game_files_written -or $proof.safety.god_of_war_launched -or
        $proof.safety.save_files_written -or $proof.safety.progression_state_written -or
        $proof.safety.marker_state_written -or $proof.safety.runtime_installer_executed) {
        throw 'Stage A offline safety proof is not clean.'
    }

    $properties = @($proof.files.PSObject.Properties)
    if ($properties.Count -ne @($files.Keys).Count) { throw 'Stage A proof must contain exactly four files.' }
    $expectedPaths = @($files.Values | ForEach-Object { ([string]$_).Replace('\','/') } | Sort-Object)
    $actualPaths = @($properties.Name | ForEach-Object { ([string]$_).Replace('\','/') } | Sort-Object)
    if (($expectedPaths -join "`n") -ne ($actualPaths -join "`n")) { throw 'Stage A proof file set changed.' }
    foreach ($name in $files.Keys) {
        $relative = ([string]$files[$name]).Replace('\','/')
        $entry = $proof.files.PSObject.Properties[$relative]
        if ($null -eq $entry -or ([string]$entry.Value.sha256).ToLowerInvariant() -ne $approvedCandidateShas[$name]) {
            throw "Stage A proof SHA changed: $name"
        }
    }
    return $proof
}

function Assert-StageACandidate {
    [void](Assert-StageAProof)
    if (-not (Test-Path -LiteralPath $candidateRoot -PathType Container)) { throw "Stage A candidate missing: $candidateRoot" }
    $diskFiles = @(Get-ChildItem -LiteralPath $candidateRoot -Recurse -File | ForEach-Object {
        Get-SafeRelativePath -Root $candidateRoot -Path $_.FullName -Label 'Stage A candidate file'
    } | Sort-Object)
    $expected = @($files.Values | ForEach-Object { ([string]$_).Replace('\','/') } | Sort-Object)
    if (($diskFiles -join "`n") -ne ($expected -join "`n")) { throw 'Stage A candidate must contain exactly the approved four files.' }
    foreach ($name in $files.Keys) {
        $source = Resolve-SafeChildPath -Root $candidateRoot -Relative ([string]$files[$name]) -Label 'Stage A candidate source'
        if ((Get-Sha256 $source) -ne $approvedCandidateShas[$name]) { throw "Stage A candidate SHA mismatch: $name" }
    }
}

function Assert-FrozenRavenMapFiles([string]$Game) {
    foreach ($name in $files.Keys) {
        $path = Resolve-SafeChildPath -Root $Game -Relative ([string]$files[$name]) -Label 'frozen Raven map file'
        if ((Get-Sha256 $path) -ne $frozenRavenShas[$name]) { throw "Frozen Raven map file changed: $name" }
    }
}

function Get-StageARollbackCheckInstalled([string]$Status) {
    if ($Status -eq 'installed') { return $true }
    if ($Status -in @(
        'backup-complete', 'installing', 'rolling-back',
        'rolling-back-after-install-failure', 'rollback-failed-after-install-failure'
    )) {
        # Interrupted recovery stays non-force. Restore-State accepts only exact
        # before/candidate bytes and verifies every backup before first write.
        return $false
    }
    throw "Stage A transaction status '$Status' cannot be rolled back."
}

if ($LibraryOnly) { return }

if ($Mode -eq 'Status') {
    Write-Host 'RAVEN_TWIN_STAGE_A_RUNTIME_STATUS'
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
Assert-TrackedTreeClean
Assert-GameClosed -Game $GameRoot
$operationHead = Get-RepoHead

if ($Mode -eq 'Install') {
    if (-not $ConfirmRuntimeTest) {
        throw 'Stage A install is disarmed. Use -ConfirmRuntimeTest only for the separate approved human map-open test.'
    }
    Assert-StageACandidate
    if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
        $old = Get-ValidatedActiveTransaction -Active $activeManifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -ProofPath $archivedReport -FileMap $files -CandidateShas $approvedCandidateShas -CandidateLabel $candidateLabel -RepoBranch $branch
        if ([string]$old.status -notin @('rolled-back','rolled-back-after-install-failure')) { throw "Active Stage A transaction exists with status '$($old.status)'." }
    }

    Assert-FrozenRavenMapFiles -Game $GameRoot
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verification failed before Stage A install.' }

    $preWriteValidation = {
        [void](Assert-Branch)
        Assert-RepoHead -ExpectedHead $operationHead
        Assert-TrackedTreeClean
        Assert-GameClosed -Game $GameRoot
        Assert-FrozenRavenMapFiles -Game $GameRoot
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven verification failed after backup and before first Stage A write.' }
        Assert-GameClosed -Game $GameRoot
    }
    $writeGuard = {
        Assert-GameClosed -Game $GameRoot
        Assert-RepoHead -ExpectedHead $operationHead
        Assert-TrackedTreeClean
    }
    $manifest = Invoke-TransactionalInstall -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -FileMap $files -CandidateShas $approvedCandidateShas -CandidateLabel $candidateLabel -RepoBranch $branch -RepoHead $operationHead -ProofPath $archivedReport -PreWriteValidation $preWriteValidation -WriteGuard $writeGuard

    Write-Host 'RAVEN_TWIN_STAGE_A_INSTALLED_FOR_HUMAN_RUNTIME_TEST'
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host '  files installed: 4 map-only files'
    Write-Host '  game launched by installer: false'
    Write-Host '  saves/progression/marker state written: false'
    Write-Host "  manifest: $(Join-Path ([string]$manifest.transaction_root) 'manifest.json')"
    exit 0
}

if ($Mode -eq 'Rollback') {
    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) { throw 'No Stage A transaction exists.' }
    [void](Assert-StageAProof)
    $manifest = Get-ValidatedActiveTransaction -Active $activeManifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -ProofPath $archivedReport -FileMap $files -CandidateShas $approvedCandidateShas -CandidateLabel $candidateLabel -RepoBranch $branch
    $checkInstalled = Get-StageARollbackCheckInstalled -Status ([string]$manifest.status)
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
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Stage A rollback restored files, but Raven production verification failed.' }
    Write-Host 'RAVEN_TWIN_STAGE_A_ROLLED_BACK'
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host '  exact pre-install state restored: true'
    Write-Host '  Raven production verifier passed: true'
    exit 0
}
