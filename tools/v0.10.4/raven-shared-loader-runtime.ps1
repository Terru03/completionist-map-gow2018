param(
    [ValidateSet('Install','Rollback','Status')]
    [string]$Mode = 'Status',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$ConfirmRuntimeTest,
    [switch]$LibraryOnly
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# Load pinned engine functions only. Retired payloads never installed.
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
$expectedBranch = 'codex/v104-raven-shared-loader-twin'
$stateRoot = Join-Path $repo 'build/v0.10.4-raven-shared-loader/runtime/transaction'
$activeManifest = Join-Path $stateRoot 'active.json'
$candidateRoot = Join-Path $repo 'build/v0.10.4-raven-shared-loader/offline/candidate/game-root'
$archivedReport = Join-Path $repo 'archive/field-logs/completionist-v104-raven-shared-loader-offline.json'
$candidateLabel = 'raven-shared-loader'
$files = [ordered]@{
    'mapmaster.dcb' = 'exec/dc/pc_le/mapmaster.dcb'
    'mapcoords.dcb' = 'exec/dc/pc_le/mapcoords.dcb'
    'wad_r_ui.dcb' = 'exec/dc/pc_le/wad_r_ui.dcb'
    'mapmenu.lua' = 'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
}
$frozenRavenShas = [ordered]@{
    'mapmaster.dcb' = 'b930c51316ca136d9c40ea7cda6a63a051127b357e97f1d4e4eb96a16993d96f'
    'mapcoords.dcb' = '945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb'
    'wad_r_ui.dcb' = '765ef6c08a3c9d52ed9485c184237bc3fdde103feef01c496a6999fdbea8826d'
    'mapmenu.lua' = '67d069a798417b631c271f48c129fb2083591b81a31859ab94769fbbb8b01c6b'
}
$approvedCandidateShas = [ordered]@{
    'mapmaster.dcb' = '1e1d5086815bc8553490bff915fea210a8be4f80ce6c88b418b62d7050690a31'
    'mapcoords.dcb' = '36bd16f8f21c6387b556e156055ea02f5c262b30a6c450cc0efa05734efb1a0c'
    'wad_r_ui.dcb' = '9a434a29ed2e333362e60ac7f224d26855fc9dc86834aa94504a170854e22f2b'
    'mapmenu.lua' = '8cadf91d08a60211686f1e9634d13d56a25bf4eab75e8975c83763d99ad4ee5d'
}

function Assert-SharedLoaderProof {
    $proof = Get-Content -LiteralPath $archivedReport -Raw | ConvertFrom-Json
    if ($proof.result -ne 'RAVEN_SHARED_LOADER_OFFLINE_PROOF_PASSED' -or
        $proof.branch_contract -ne $expectedBranch -or
        $proof.base_head -ne '8abf20bafe4534c798daa62d2ef5a70c50ecb056' -or
        $proof.ready_for_runtime_test -ne $true -or $proof.runtime_test_performed -ne $false -or
        $proof.all_four_files_inverse_exact -ne $true -or $proof.game_files_written -ne $false -or
        $proof.retired_candidates_used -ne $false -or $proof.progression_or_marker_state_writes -ne $false) {
        throw 'Shared Loader offline gate differs.'
    }
    if ($proof.identities.loader -ne 'goMapIconCompletionistRaven' -or
        $proof.identities.resource_hash -ne '584F31DC8BD6E738' -or
        $proof.identities.raven_uid -ne 'E15E6BC82AE2773E' -or
        $proof.identities.twin_uid -ne '2F530E7F3F156D90' -or $proof.identities.init_state -ne 0) {
        throw 'Shared Loader identity contract differs.'
    }
    $expected = @($files.Values | Sort-Object)
    $actual = @($proof.files.PSObject.Properties.Name | Sort-Object)
    if (($expected -join "`n") -ne ($actual -join "`n")) { throw 'Proof file set differs.' }
    foreach ($name in $files.Keys) {
        $relative = [string]$files[$name]
        if ($proof.files.PSObject.Properties[$relative].Value.sha256 -ne $approvedCandidateShas[$name] -or
            $proof.proofs.PSObject.Properties[$relative].Value.normalized_to_frozen_raven_exact -ne $true -or
            $proof.source_sha256.PSObject.Properties[$relative].Value -ne $frozenRavenShas[$name]) {
            throw "Shared Loader hash/inverse proof differs: $name"
        }
    }
    return $proof
}

function Assert-SharedLoaderCandidate {
    [void](Assert-SharedLoaderProof)
    if (-not (Test-Path -LiteralPath $candidateRoot -PathType Container)) { throw 'Candidate missing.' }
    $actual = @(Get-ChildItem -LiteralPath $candidateRoot -Recurse -File | ForEach-Object {
        Get-SafeRelativePath -Root $candidateRoot -Path $_.FullName -Label 'Shared Loader candidate'
    } | Sort-Object)
    $expected = @($files.Values | Sort-Object)
    if (($actual -join "`n") -ne ($expected -join "`n")) { throw 'Candidate must contain exactly four approved files.' }
    foreach ($name in $files.Keys) {
        $path = Resolve-SafeChildPath -Root $candidateRoot -Relative $files[$name] -Label 'candidate'
        if ((Get-Sha256 $path) -ne $approvedCandidateShas[$name]) { throw "Candidate SHA differs: $name" }
    }
}

function Assert-FrozenRavenMapFiles([string]$Game) {
    foreach ($name in $files.Keys) {
        $path = Resolve-SafeChildPath -Root $Game -Relative $files[$name] -Label 'frozen Raven'
        if ((Get-Sha256 $path) -ne $frozenRavenShas[$name]) { throw "Frozen Raven SHA differs: $name" }
    }
}

function Invoke-SharedLoaderRavenVerifier([string]$Game) {
    $verifier = Join-Path $PSScriptRoot 'verify-raven-production-state.py'
    $output = Join-Path $repo 'build/v0.10.4-raven-shared-loader/runtime/frozen-raven-verification.json'
    & py.exe -3 $verifier --game-root $Game --repo-root $repo --output $output | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verifier failed.' }
}

function Get-SharedLoaderRollbackCheckInstalled([string]$Status) {
    if ($Status -eq 'installed') { return $true }
    if ($Status -in @('backup-complete','installing','rolling-back',
        'rolling-back-after-install-failure','rollback-failed-after-install-failure')) { return $false }
    throw "Transaction state cannot roll back: $Status"
}

if ($LibraryOnly) { return }
if ($Mode -eq 'Status') {
    Write-Host 'RAVEN_SHARED_LOADER_RUNTIME_STATUS'
    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) {
        Write-Host '  active transaction: none'
        exit 0
    }
    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host "  status: $($manifest.status)"
    Write-Host '  visual proof: inspect human report and loader log'
    exit 0
}
if ($Mode -eq 'Install' -and -not $ConfirmRuntimeTest) { throw 'Install disarmed. Manual test needs -ConfirmRuntimeTest.' }
Assert-PathTopology -Game $GameRoot -Candidate $candidateRoot -State $stateRoot
Assert-GameRootIdentity -Game $GameRoot
$branch = Assert-Branch
Assert-TrackedTreeClean
Assert-GameClosed -Game $GameRoot
$operationHead = Get-RepoHead
$writeGuard = {
    [void](Assert-Branch)
    Assert-GameClosed -Game $GameRoot
    Assert-RepoHead -ExpectedHead $operationHead
    Assert-TrackedTreeClean
}

if ($Mode -eq 'Install') {
    Assert-SharedLoaderCandidate
    if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
        $old = Get-ValidatedActiveTransaction -Active $activeManifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -ProofPath $archivedReport -FileMap $files -CandidateShas $approvedCandidateShas -CandidateLabel $candidateLabel -RepoBranch $branch
        if ($old.status -notin @('rolled-back','rolled-back-after-install-failure')) { throw 'Active transaction exists.' }
    }
    Assert-FrozenRavenMapFiles -Game $GameRoot
    Invoke-SharedLoaderRavenVerifier -Game $GameRoot
    $preWriteValidation = {
        & $writeGuard
        Assert-FrozenRavenMapFiles -Game $GameRoot
        Invoke-SharedLoaderRavenVerifier -Game $GameRoot
        Assert-GameClosed -Game $GameRoot
    }
    $manifest = Invoke-TransactionalInstall -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -FileMap $files -CandidateShas $approvedCandidateShas -CandidateLabel $candidateLabel -RepoBranch $branch -RepoHead $operationHead -ProofPath $archivedReport -PreWriteValidation $preWriteValidation -WriteGuard $writeGuard
    Write-Host 'RAVEN_SHARED_LOADER_INSTALLED_FOR_HUMAN_TEST'
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host '  game launched: false'
    Write-Host '  files: two marker DCBs, additive pool row, Twin map hook'
    exit 0
}

if ($Mode -eq 'Rollback') {
    [void](Assert-SharedLoaderProof)
    $manifest = Get-ValidatedActiveTransaction -Active $activeManifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -ProofPath $archivedReport -FileMap $files -CandidateShas $approvedCandidateShas -CandidateLabel $candidateLabel -RepoBranch $branch
    $checkInstalled = Get-SharedLoaderRollbackCheckInstalled -Status $manifest.status
    Restore-State -Manifest $manifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -ProofPath $archivedReport -FileMap $files -CandidateShas $approvedCandidateShas -CandidateLabel $candidateLabel -RepoBranch $branch -CheckInstalled $checkInstalled -Force $false -WriteGuard $writeGuard
    $manifest.status = 'rolled-back'
    $manifest.rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
    Save-TransactionManifest -Manifest $manifest -Active $activeManifest
    Assert-FrozenRavenMapFiles -Game $GameRoot
    Invoke-SharedLoaderRavenVerifier -Game $GameRoot
    Write-Host 'RAVEN_SHARED_LOADER_ROLLED_BACK'
    Write-Host '  exact pre-install bytes restored: true'
    exit 0
}
