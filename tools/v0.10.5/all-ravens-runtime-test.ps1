param(
    [ValidateSet('Install','Rollback','Status')]
    [string]$Mode = 'Status',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$ConfirmRuntimeTest,
    [switch]$PreserveCurrentBaseline
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$engine = Join-Path $repo 'tools\v0.10.4\nornir-runtime-candidate3.ps1'
if (-not (Test-Path -LiteralPath $engine -PathType Leaf)) { throw "Missing transaction engine: $engine" }
. $engine -Mode $Mode -GameRoot $GameRoot -ConfirmRuntimeTest:$ConfirmRuntimeTest -LibraryOnly

$expectedBranch = 'codex/all-collectibles-production-research'
$candidateLabel = 'all-ravens-v0.10.5-catalogue-first'
$candidateRoot = Join-Path $repo 'build\v0.10.5-all-ravens-release-candidate\offline\candidate\game-root'
$proofPath = Join-Path $repo 'archive\all-ravens\all-ravens-release-candidate-offline.json'
$stateRoot = Join-Path $repo 'build\v0.10.5-all-ravens-runtime-test\transaction'
$activeManifest = Join-Path $stateRoot 'active.json'

$files = [ordered]@{
    mapmaster = 'exec/dc/pc_le/mapmaster.dcb'
    mapcoords  = 'exec/dc/pc_le/mapcoords.dcb'
    ui         = 'exec/dc/pc_le/wad_r_ui.dcb'
    mapmenu    = 'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
    mainhud    = 'mods/lua/gameart/ui/scripts/hud/mainhud.lua'
    coresave   = 'mods/lua/gameart/scripts/libraries/core/save.lua'
    events     = 'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua'
}

function Assert-AllRavensBranch {
    $branch = (& git -C $repo branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not determine Git branch.' }
    if ($branch -ne $expectedBranch) { throw "Expected branch '$expectedBranch', got '$branch'." }
    return $branch
}

function Assert-AllRavensProof {
    if (-not (Test-Path -LiteralPath $proofPath -PathType Leaf)) { throw "Missing proof: $proofPath" }
    $proof = Get-Content -LiteralPath $proofPath -Raw | ConvertFrom-Json
    if ([int]$proof.schema -ne 1) { throw 'Unexpected all-Ravens proof schema.' }
    if ([string]$proof.result -ne 'ALL_RAVENS_OFFLINE_CANDIDATE_READY_FOR_RUNTIME_TEST') { throw 'All-Ravens proof is not runtime-test-ready.' }
    if (-not [bool]$proof.ready_for_runtime_test) { throw 'All-Ravens runtime-test gate is closed.' }
    if ([string]$proof.branch -ne $expectedBranch) { throw 'All-Ravens proof branch differs.' }
    if ([int]$proof.catalogue_entries -ne 53) { throw 'All-Ravens proof does not contain exactly 53 catalogue entries.' }
    if ([bool]$proof.game_files_written -or [bool]$proof.game_launched -or [bool]$proof.save_or_progression_touched) { throw 'All-Ravens proof safety state is not clean.' }
    if ([bool]$proof.state.writes_progression) { throw 'All-Ravens runtime unexpectedly writes progression.' }
    if ([string]$proof.state.unknown_state_policy -ne 'show catalogue marker unless confirmed killed') { throw 'Unexpected unknown-state policy.' }
    if (-not [bool]$proof.state.persisted_kill_bootstrap) { throw 'Persisted-kill bootstrap contract is missing.' }

    $properties = @($proof.files.PSObject.Properties)
    if ($properties.Count -ne 7) { throw "All-Ravens proof must contain exactly seven files; found $($properties.Count)." }
    $expectedPaths = @($files.Values | ForEach-Object { ([string]$_).Replace('\','/') } | Sort-Object)
    $actualPaths = @($properties.Name | ForEach-Object { ([string]$_).Replace('\','/') } | Sort-Object)
    if (($expectedPaths -join "`n") -ne ($actualPaths -join "`n")) { throw 'All-Ravens proof file set differs from the approved seven-file set.' }
    return $proof
}

function Get-AllRavensCandidateShas([object]$Proof) {
    $result = [ordered]@{}
    foreach ($name in $files.Keys) {
        $relative = ([string]$files[$name]).Replace('\','/')
        $entry = $Proof.files.PSObject.Properties[$relative]
        if ($null -eq $entry) { throw "Proof misses file: $relative" }
        $sha = ([string]$entry.Value.sha256).ToLowerInvariant()
        if ($sha -notmatch '^[0-9a-f]{64}$') { throw "Invalid candidate SHA: $relative" }
        $result[$name] = $sha
    }
    return $result
}

function Assert-AllRavensCandidate([object]$Proof, [System.Collections.IDictionary]$CandidateShas) {
    if (-not (Test-Path -LiteralPath $candidateRoot -PathType Container)) { throw "Missing candidate root: $candidateRoot" }
    $diskFiles = @(Get-ChildItem -LiteralPath $candidateRoot -Recurse -File | ForEach-Object {
        Get-SafeRelativePath -Root $candidateRoot -Path $_.FullName -Label 'all-Ravens candidate file'
    } | Sort-Object)
    $approved = @($files.Values | ForEach-Object { ([string]$_).Replace('\','/') } | Sort-Object)
    if (($diskFiles -join "`n") -ne ($approved -join "`n")) { throw 'All-Ravens candidate root contains a missing or unexpected file.' }
    foreach ($name in $files.Keys) {
        $relative = ([string]$files[$name]).Replace('\','/')
        $source = Resolve-SafeChildPath -Root $candidateRoot -Relative $relative -Label 'all-Ravens candidate source'
        if ((Get-Sha256 $source) -ne ([string]$CandidateShas[$name]).ToLowerInvariant()) { throw "Candidate SHA mismatch: $relative" }
    }
}

function Assert-ExpectedPreInstallGame([object]$Proof) {
    foreach ($name in $files.Keys) {
        $relative = ([string]$files[$name]).Replace('\','/')
        $entry = $Proof.source_sha256.PSObject.Properties[$relative]
        if ($null -eq $entry) { throw "Proof misses pre-install source SHA: $relative" }
        $expected = ([string]$entry.Value).ToLowerInvariant()
        $path = Resolve-SafeChildPath -Root $GameRoot -Relative $relative -Label 'installed game source'
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            if ($name -eq 'coresave') { continue }
            throw "Installed game file missing: $relative"
        }
        $actual = Get-Sha256 $path
        if ($actual -ne $expected) { throw "Installed game baseline differs for $relative. Expected $expected, got $actual." }
    }
}

function Assert-CurrentPreInstallGamePresent {
    foreach ($name in $files.Keys) {
        $relative = ([string]$files[$name]).Replace('\','/')
        $path = Resolve-SafeChildPath -Root $GameRoot -Relative $relative -Label 'installed game source'
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            if ($name -eq 'coresave') { continue }
            throw "Installed game file missing: $relative"
        }
        $sha = Get-Sha256 $path
        if ($sha -notmatch '^[0-9a-f]{64}$') { throw "Could not hash installed game file: $relative" }
    }
}

function Assert-ManifestBeforeState([object]$Manifest) {
    foreach ($entry in @($Manifest.entries)) {
        $relative = ([string]$entry.relative).Replace('\','/')
        $path = Resolve-SafeChildPath -Root $GameRoot -Relative $relative -Label 'restored game file'
        if ([bool]$entry.existed_before) {
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Restored game file missing: $relative" }
            $expected = ([string]$entry.before_sha256).ToLowerInvariant()
            $actual = Get-Sha256 $path
            if ($actual -ne $expected) { throw "Restored game baseline differs for $relative. Expected $expected, got $actual." }
        }
        elseif (Test-Path -LiteralPath $path) {
            throw "Rollback left a file that did not exist before install: $relative"
        }
    }
}

function Assert-PreInstallPolicy([object]$Proof) {
    if ($PreserveCurrentBaseline) {
        Assert-CurrentPreInstallGamePresent
    }
    else {
        Assert-ExpectedPreInstallGame -Proof $Proof
    }
}

function Assert-RestoredGame([object]$Proof, [object]$Manifest) {
    if ($PreserveCurrentBaseline) {
        Assert-ManifestBeforeState -Manifest $Manifest
    }
    else {
        Assert-ExpectedPreInstallGame -Proof $Proof
    }
}

function Assert-TerminalAllRavensTransactionSummary([object]$Manifest) {
    if ([string]$Manifest.status -notin @('rolled-back','rolled-back-after-install-failure')) {
        throw "Transaction status '$($Manifest.status)' is not terminal."
    }
    if ([string]$Manifest.candidate -ne $candidateLabel) {
        throw "Terminal transaction belongs to a different candidate: $($Manifest.candidate)"
    }
    if ([string]$Manifest.repo_branch -ne $expectedBranch) {
        throw "Terminal transaction branch differs: $($Manifest.repo_branch)"
    }
    if ([string]$Manifest.transaction_id -notmatch '^\d{8}T\d{6}Z-[0-9a-f]{8}$') {
        throw 'Terminal transaction ID is invalid.'
    }
    if ((Get-FullPath ([string]$Manifest.game_root)) -ne (Get-FullPath $GameRoot)) {
        throw "Terminal transaction belongs to a different game root: $($Manifest.game_root)"
    }
    $terminalEntryCount = @($Manifest.entries).Count
    if ($terminalEntryCount -notin @(5, 6, @($files.Keys).Count)) {
        throw "Terminal transaction entry count differs: $terminalEntryCount"
    }
    return $Manifest
}

if ($Mode -eq 'Status') {
    Write-Host 'ALL_RAVENS_RUNTIME_TEST_STATUS'
    Write-Host "  candidate: $candidateRoot"
    Write-Host "  proof: $proofPath"
    Write-Host "  preserve current baseline mode: $([bool]$PreserveCurrentBaseline)"
    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) {
        Write-Host '  active transaction: none'
        exit 0
    }
    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host "  status: $($manifest.status)"
    Write-Host "  files: $(@($manifest.entries).Count)"
    Write-Host "  transaction root: $($manifest.transaction_root)"
    exit 0
}

if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }
$proof = Assert-AllRavensProof
$candidateShas = Get-AllRavensCandidateShas -Proof $proof
Assert-AllRavensCandidate -Proof $proof -CandidateShas $candidateShas
Assert-PathTopology -Game $GameRoot -Candidate $candidateRoot -State $stateRoot
Assert-GameRootIdentity -Game $GameRoot
$branch = Assert-AllRavensBranch
Assert-TrackedTreeClean
Assert-GameClosed -Game $GameRoot
$operationHead = Get-RepoHead

if ($Mode -eq 'Install') {
    if (-not $ConfirmRuntimeTest) { throw 'Install is disarmed. Re-run with -ConfirmRuntimeTest for the controlled 53-Raven field test.' }
    Assert-PreInstallPolicy -Proof $proof

    if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
        $activeSummary = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
        if ([string]$activeSummary.status -in @('rolled-back','rolled-back-after-install-failure')) {
            [void](Assert-TerminalAllRavensTransactionSummary -Manifest $activeSummary)
            Write-Host "  previous terminal transaction retained as history: $($activeSummary.transaction_id) ($($activeSummary.status))"
            Write-Host '  historical candidate SHAs are intentionally not compared with the replacement candidate'
        }
        else {
            $old = Get-ValidatedActiveTransaction -Active $activeManifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -ProofPath $proofPath -FileMap $files -CandidateShas $candidateShas -CandidateLabel $candidateLabel -RepoBranch $branch
            throw "Active all-Ravens transaction already exists with status '$($old.status)'. Roll it back first."
        }
    }

    $preWriteValidation = {
        [void](Assert-AllRavensBranch)
        Assert-RepoHead -ExpectedHead $operationHead
        Assert-TrackedTreeClean
        Assert-GameClosed -Game $GameRoot
        Assert-PreInstallPolicy -Proof $proof
    }
    $writeGuard = {
        Assert-GameClosed -Game $GameRoot
        Assert-RepoHead -ExpectedHead $operationHead
        Assert-TrackedTreeClean
    }

    $manifest = Invoke-TransactionalInstall -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -FileMap $files -CandidateShas $candidateShas -CandidateLabel $candidateLabel -RepoBranch $branch -RepoHead $operationHead -ProofPath $proofPath -PreWriteValidation $preWriteValidation -WriteGuard $writeGuard

    Write-Host 'ALL_RAVENS_RUNTIME_TEST_INSTALLED'
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host '  files installed: 7'
    Write-Host '  catalogue Ravens in candidate: 53'
    Write-Host '  backups completed before first game write: true'
    Write-Host '  candidate SHA verification: true'
    Write-Host "  pre-install rollback baseline: $(if ($PreserveCurrentBaseline) { 'current seven-file state' } else { 'frozen v3.3 source state' })"
    Write-Host '  saves/progression written by installer: false'
    Write-Host '  game launched by installer: false'
    Write-Host "  manifest: $(Join-Path ([string]$manifest.transaction_root) 'manifest.json')"
    exit 0
}

if ($Mode -eq 'Rollback') {
    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) { throw 'No all-Ravens runtime-test transaction exists.' }
    $manifest = Get-ValidatedActiveTransaction -Active $activeManifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -ProofPath $proofPath -FileMap $files -CandidateShas $candidateShas -CandidateLabel $candidateLabel -RepoBranch $branch
    Assert-RollbackStatus -Status ([string]$manifest.status) -Force $false
    $writeGuard = {
        Assert-GameClosed -Game $GameRoot
        Assert-RepoHead -ExpectedHead $operationHead
        Assert-TrackedTreeClean
    }
    Restore-State -Manifest $manifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -ProofPath $proofPath -FileMap $files -CandidateShas $candidateShas -CandidateLabel $candidateLabel -RepoBranch $branch -CheckInstalled $true -Force $false -WriteGuard $writeGuard
    $manifest.status = 'rolled-back'
    $manifest.rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
    Save-TransactionManifest -Manifest $manifest -Active $activeManifest
    Assert-RestoredGame -Proof $proof -Manifest $manifest

    Write-Host 'ALL_RAVENS_RUNTIME_TEST_ROLLED_BACK'
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host '  exact seven-file pre-install state restored: true'
    Write-Host '  source SHA verification: true'
    Write-Host '  saves/progression touched by rollback: false'
    exit 0
}
