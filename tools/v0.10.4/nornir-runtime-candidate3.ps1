param(
    [ValidateSet('Install','Rollback','Status')]
    [string]$Mode = 'Status',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$ForceRollback,
    [switch]$ConfirmRuntimeTest,
    [switch]$LibraryOnly
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedBranch = 'codex/v104-raven-production'
$stateRoot = Join-Path $repo 'build\v0.10.4-nornir-runtime-candidate3\transaction'
$activeManifest = Join-Path $stateRoot 'active.json'
$candidateRoot = Join-Path $repo 'build\v0.10.4-nornir-candidate3\offline\candidate\game-root'
$archivedReport = Join-Path $repo 'archive\field-logs\completionist-v104-nornir-candidate3-offline-reconstruction.json'
$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$expectedCandidateWad = '90391a2841d3a9ad889b95d5c17fc0ee09de803a57675b6d237a98051b08c660'
$retiredCandidate2Wad = '96772dd9e36e1d3050ad936dbb9d8d8dfadb39ed2d7b4f74e400c2844877acef'
$donorMaterialQ20 = 'D595197B0961F689'

$files = [ordered]@{
    'r_ui.wad' = 'exec/wad/pc_le/r_ui.wad'
    'wad_r_ui.dcb' = 'exec/dc/pc_le/wad_r_ui.dcb'
    'wad_r_perm.dcb' = 'exec/dc/pc_le/wad_r_perm.dcb'
    'mapmaster.dcb' = 'exec/dc/pc_le/mapmaster.dcb'
    'mapcoords.dcb' = 'exec/dc/pc_le/mapcoords.dcb'
    'compassgraph.dcb' = 'exec/dc/pc_le/compassgraph.dcb'
    'mapmenu.lua' = 'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
    'mainhud.lua' = 'mods/lua/gameart/ui/scripts/hud/mainhud.lua'
    'interact_chest_runic.lua' = 'mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_runic.lua'
    'interact_chest_standard.lua' = 'mods/lua/gameart/scripts/levels/gameplaymodules/progression/interact_chest_standard.lua'
}

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-FullPath([string]$Path) {
    return [IO.Path]::GetFullPath($Path)
}

function Test-PathWithin([string]$Parent, [string]$Child) {
    $parentFull = (Get-FullPath $Parent).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $childFull = Get-FullPath $Child
    if ($childFull.Equals($parentFull, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    $prefix = $parentFull + [IO.Path]::DirectorySeparatorChar
    return $childFull.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function Resolve-SafeChildPath([string]$Root, [string]$Relative, [string]$Label) {
    if ([IO.Path]::IsPathRooted($Relative)) { throw "$Label must be relative: $Relative" }
    $full = Get-FullPath (Join-Path $Root $Relative)
    if (-not (Test-PathWithin -Parent $Root -Child $full)) { throw "$Label escapes root: $Relative" }
    return $full
}

function Assert-PathTopology([string]$Game, [string]$Candidate, [string]$State) {
    $gameFull = Get-FullPath $Game
    $candidateFull = Get-FullPath $Candidate
    $stateFull = Get-FullPath $State
    $repoFull = Get-FullPath $repo
    if (-not (Test-PathWithin -Parent $repoFull -Child $candidateFull)) { throw 'Candidate root must stay inside the repository build tree.' }
    if (-not (Test-PathWithin -Parent $repoFull -Child $stateFull)) { throw 'Transaction state must stay inside the repository build tree.' }
    if (Test-PathWithin -Parent $gameFull -Child $candidateFull) { throw 'Candidate root must not be inside the installed game.' }
    if (Test-PathWithin -Parent $gameFull -Child $stateFull) { throw 'Transaction state must not be inside the installed game.' }
    if (Test-PathWithin -Parent $candidateFull -Child $gameFull) { throw 'Installed game must not be inside the Candidate 3 output tree.' }
}

function Assert-GameClosed {
    if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War first.' }
    if (Get-Process -Name GodOfWar -ErrorAction SilentlyContinue) { throw 'Close God of War first.' }
}

function Assert-Branch {
    $branch = (& git -C $repo branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not determine Git branch.' }
    if ($branch -ne $expectedBranch) { throw "Expected branch '$expectedBranch', got '$branch'." }
    return $branch
}

function Assert-TrackedTreeClean {
    & git -C $repo diff --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) { throw 'Tracked working-tree changes exist. Commit or revert them before Candidate 3 runtime work.' }
    & git -C $repo diff --cached --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) { throw 'Staged changes exist. Commit or unstage them before Candidate 3 runtime work.' }
}

function Write-JsonAtomic([object]$Value, [string]$Path) {
    $parent = Split-Path $Path -Parent
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $temp = "$Path.tmp-$([Guid]::NewGuid().ToString('N'))"
    $encoding = New-Object System.Text.UTF8Encoding($false)
    try {
        $json = $Value | ConvertTo-Json -Depth 30
        [IO.File]::WriteAllText($temp, $json + [Environment]::NewLine, $encoding)
        Move-Item -LiteralPath $temp -Destination $Path -Force
    }
    finally {
        Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
    }
}

function Copy-Verified([string]$Source, [string]$Destination, [string]$ExpectedSha) {
    New-Item -ItemType Directory -Force -Path (Split-Path $Destination -Parent) | Out-Null
    $temp = "$Destination.completionist-tmp-$([Guid]::NewGuid().ToString('N'))"
    try {
        Copy-Item -LiteralPath $Source -Destination $temp -Force
        if ((Get-Sha256 $temp) -ne $ExpectedSha.ToLowerInvariant()) { throw "Temporary SHA mismatch: $Destination" }
        Move-Item -LiteralPath $temp -Destination $Destination -Force
        if ((Get-Sha256 $Destination) -ne $ExpectedSha.ToLowerInvariant()) { throw "Destination SHA mismatch: $Destination" }
    }
    finally {
        Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
    }
}

function Assert-ProofObject([object]$Proof) {
    if ($Proof.result -ne 'NORNIR_CANDIDATE3_OFFLINE_ASSEMBLED') { throw 'Unexpected Candidate 3 proof result.' }
    if ($Proof.branch_contract -ne $expectedBranch) { throw 'Candidate 3 proof branch contract changed.' }
    if ($Proof.candidate3.runtime_install_allowed) { throw 'Candidate 3 proof unexpectedly allows runtime installation.' }
    if ($Proof.candidate3.wad.candidate3_sha256 -ne $expectedCandidateWad) { throw 'Candidate 3 WAD identity changed.' }
    if ($Proof.candidate3.wad.candidate2_retired_sha256 -ne $retiredCandidate2Wad) { throw 'Retired Candidate 2 anchor changed.' }
    if ($Proof.candidate3.wad.material.preserved_raven_donor_qword_0x20 -ne $donorMaterialQ20) { throw 'Candidate 3 donor material +0x20 rule changed.' }
    if ([int]$Proof.candidate3.wad.model_groups.dedicated_nornir_mg_records -ne 0) { throw 'Candidate 3 unexpectedly contains dedicated Nornir MG records.' }
    if ($Proof.candidate3.wad.model_groups.opaque_mg_payload_bytes_changed) { throw 'Candidate 3 changes opaque MG payload bytes.' }
    if ($Proof.candidate3.wad.preservation.stock_dock_and_boatdock_definitions_mutated) { throw 'Candidate 3 mutates stock Dock/BoatDock definitions.' }
    if (-not $Proof.candidate3.wad.candidate3_reparse_roundtrip_exact) { throw 'Candidate 3 WAD round-trip proof failed.' }
    if (-not $Proof.candidate3.wad.candidate3_normalizes_exactly_to_frozen_raven) { throw 'Candidate 3 no longer normalizes to frozen Raven.' }
    if (-not $Proof.proofs.started_from_frozen_raven_production) { throw 'Candidate 3 baseline proof is missing.' }
    if ($Proof.proofs.candidate2_used_as_input) { throw 'Candidate 2 must never be an input to Candidate 3.' }
    if (-not $Proof.proofs.stock_dock_boatdock_definitions_unchanged) { throw 'Stock Dock/BoatDock preservation proof failed.' }
    if (-not $Proof.proofs.stock_mg_payloads_unchanged) { throw 'Stock ModelGroup payload preservation proof failed.' }
    if (-not $Proof.proofs.raven_resources_preserved -or -not $Proof.proofs.raven_files_unchanged_before_after) { throw 'Frozen Raven preservation proof failed.' }
    if (-not $Proof.proofs.complete_sha_manifest) { throw 'Candidate 3 SHA manifest is incomplete.' }
    if ($Proof.safety.god_of_war_launched -or $Proof.safety.installed_game_files_written -or $Proof.safety.save_files_written -or $Proof.safety.progression_state_written -or $Proof.safety.marker_state_written) {
        throw 'Candidate 3 offline proof safety contract is not clean.'
    }
    if ($Proof.safety.runtime_install_allowed) { throw 'Candidate 3 archive must remain runtime_install_allowed=false before the field test.' }

    $properties = @($Proof.candidate3.files.PSObject.Properties)
    if ($properties.Count -ne 10) { throw "Candidate 3 proof must contain exactly ten files; found $($properties.Count)." }
    $expected = @($files.Values | ForEach-Object { ([string]$_).Replace('\','/') } | Sort-Object)
    $actual = @($properties.Name | ForEach-Object { ([string]$_).Replace('\','/') } | Sort-Object)
    if (($expected -join "`n") -ne ($actual -join "`n")) { throw 'Candidate 3 proof file set differs from the approved ten-file set.' }
}

function Assert-Candidate3 {
    foreach ($required in @($candidateRoot, $archivedReport, $verifyRaven)) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Missing Candidate 3 prerequisite: $required`nRe-run .\tools\v0.10.4\run-collectible-framework-offline.ps1 first."
        }
    }

    $proof = Get-Content -LiteralPath $archivedReport -Raw | ConvertFrom-Json
    Assert-ProofObject $proof

    $diskFiles = @(Get-ChildItem -LiteralPath $candidateRoot -Recurse -File | ForEach-Object {
        [IO.Path]::GetRelativePath($candidateRoot, $_.FullName).Replace('\','/')
    } | Sort-Object)
    $approved = @($files.Values | ForEach-Object { ([string]$_).Replace('\','/') } | Sort-Object)
    if (($diskFiles -join "`n") -ne ($approved -join "`n")) { throw 'Candidate 3 output root contains a missing or unexpected file.' }

    $candidateShas = [ordered]@{}
    foreach ($name in $files.Keys) {
        $relative = ([string]$files[$name]).Replace('\','/')
        $property = $proof.candidate3.files.PSObject.Properties[$relative]
        if ($null -eq $property) { throw "Missing Candidate 3 proof entry: $relative" }
        $expectedSha = ([string]$property.Value.sha256).ToLowerInvariant()
        $source = Resolve-SafeChildPath -Root $candidateRoot -Relative $relative -Label 'candidate source'
        if ((Get-Sha256 $source) -ne $expectedSha) { throw "Candidate 3 file SHA mismatch: $name" }
        $candidateShas[$name] = $expectedSha
    }

    if ($candidateShas['r_ui.wad'] -ne $expectedCandidateWad) { throw 'Candidate 3 r_ui.wad is not the approved Candidate 3 WAD.' }
    if ($candidateShas['r_ui.wad'] -eq $retiredCandidate2Wad) { throw 'Retired Candidate 2 WAD detected.' }
    return [pscustomobject]@{ proof = $proof; shas = $candidateShas }
}

function New-TransactionManifest(
    [string]$Game,
    [string]$Candidate,
    [string]$State,
    [string]$Active,
    [System.Collections.IDictionary]$FileMap,
    [System.Collections.IDictionary]$CandidateShas,
    [string]$CandidateLabel,
    [string]$RepoBranch,
    [string]$RepoHead,
    [string]$ProofPath
) {
    $transactionId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
    $transactionRoot = Join-Path $State ('transactions\' + $transactionId)
    $backupRoot = Join-Path $transactionRoot 'backup\game-root'
    $transactionManifest = Join-Path $transactionRoot 'manifest.json'
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

    $entries = @()
    foreach ($name in $FileMap.Keys) {
        $relative = ([string]$FileMap[$name]).Replace('\','/')
        $source = Resolve-SafeChildPath -Root $Candidate -Relative $relative -Label 'candidate source'
        $dest = Resolve-SafeChildPath -Root $Game -Relative $relative -Label 'game destination'
        $candidateSha = ([string]$CandidateShas[$name]).ToLowerInvariant()
        if ((Get-Sha256 $source) -ne $candidateSha) { throw "Candidate changed after proof validation: $name" }

        $existed = Test-Path -LiteralPath $dest -PathType Leaf
        $beforeSha = $null
        $backupRelative = $null
        if ($existed) {
            $beforeSha = Get-Sha256 $dest
            $backupRelative = ('backup/game-root/' + $relative)
            $backup = Resolve-SafeChildPath -Root $transactionRoot -Relative $backupRelative -Label 'backup path'
            New-Item -ItemType Directory -Force -Path (Split-Path $backup -Parent) | Out-Null
            Copy-Item -LiteralPath $dest -Destination $backup -Force
            if ((Get-Sha256 $backup) -ne $beforeSha) { throw "Backup verification failed: $name" }
        }

        $entries += [ordered]@{
            name = $name
            relative = $relative
            candidate_sha256 = $candidateSha
            existed_before = [bool]$existed
            before_sha256 = $beforeSha
            backup_relative = $backupRelative
        }
    }

    $manifest = [ordered]@{
        schema = 1
        candidate = $CandidateLabel
        transaction_id = $transactionId
        status = 'backup-complete'
        created_utc = (Get-Date).ToUniversalTime().ToString('o')
        installed_utc = $null
        rolled_back_utc = $null
        game_root = (Get-FullPath $Game)
        candidate_root = (Get-FullPath $Candidate)
        repo_branch = $RepoBranch
        repo_head = $RepoHead
        transaction_root = (Get-FullPath $transactionRoot)
        archived_proof = $ProofPath
        entries = $entries
        safety = [ordered]@{
            backup_complete_before_first_game_write = $true
            source_sha_verified_before_write = $true
            automatic_rollback_on_install_failure = $true
            save_files_written_by_installer = $false
            progression_state_written_by_installer = $false
            marker_state_written_by_installer = $false
            game_launched_by_installer = $false
        }
    }
    Write-JsonAtomic $manifest $transactionManifest
    Write-JsonAtomic $manifest $Active
    return $manifest
}

function Save-TransactionManifest([object]$Manifest, [string]$Active) {
    $transactionManifest = Join-Path ([string]$Manifest.transaction_root) 'manifest.json'
    Write-JsonAtomic $Manifest $transactionManifest
    Write-JsonAtomic $Manifest $Active
}

function Install-TransactionFiles(
    [object]$Manifest,
    [string]$Game,
    [string]$Candidate,
    [int]$FailureInjectionAfter = -1
) {
    $written = 0
    foreach ($entry in @($Manifest.entries)) {
        $source = Resolve-SafeChildPath -Root $Candidate -Relative ([string]$entry.relative) -Label 'candidate source'
        $dest = Resolve-SafeChildPath -Root $Game -Relative ([string]$entry.relative) -Label 'game destination'
        Copy-Verified -Source $source -Destination $dest -ExpectedSha ([string]$entry.candidate_sha256)
        $written++
        if ($FailureInjectionAfter -ge 0 -and $written -ge $FailureInjectionAfter) {
            throw "SELF_TEST_INJECTED_FAILURE_AFTER_$written"
        }
    }
    foreach ($entry in @($Manifest.entries)) {
        $dest = Resolve-SafeChildPath -Root $Game -Relative ([string]$entry.relative) -Label 'game destination'
        if ((Get-Sha256 $dest) -ne ([string]$entry.candidate_sha256).ToLowerInvariant()) { throw "Post-install verification failed: $($entry.name)" }
    }
}

function Restore-State([object]$Manifest, [string]$Game, [bool]$CheckInstalled, [bool]$Force) {
    if ($CheckInstalled -and -not $Force) {
        foreach ($entry in @($Manifest.entries)) {
            $dest = Resolve-SafeChildPath -Root $Game -Relative ([string]$entry.relative) -Label 'game destination'
            if (-not (Test-Path -LiteralPath $dest -PathType Leaf)) { throw "Installed file missing before rollback: $($entry.name)" }
            if ((Get-Sha256 $dest) -ne ([string]$entry.candidate_sha256).ToLowerInvariant()) {
                throw "Installed file changed since Candidate 3 install: $($entry.name). Use -ForceRollback only after reviewing it."
            }
        }
    }

    $reverse = @($Manifest.entries)
    [array]::Reverse($reverse)
    foreach ($entry in $reverse) {
        $dest = Resolve-SafeChildPath -Root $Game -Relative ([string]$entry.relative) -Label 'game destination'
        if ([bool]$entry.existed_before) {
            $backup = Resolve-SafeChildPath -Root ([string]$Manifest.transaction_root) -Relative ([string]$entry.backup_relative) -Label 'backup path'
            $beforeSha = ([string]$entry.before_sha256).ToLowerInvariant()
            if ((Get-Sha256 $backup) -ne $beforeSha) { throw "Backup SHA mismatch: $($entry.name)" }
            Copy-Verified -Source $backup -Destination $dest -ExpectedSha $beforeSha
        }
        else {
            Remove-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
            if (Test-Path -LiteralPath $dest) { throw "Could not remove newly-created file: $($entry.name)" }
        }
    }

    foreach ($entry in @($Manifest.entries)) {
        $dest = Resolve-SafeChildPath -Root $Game -Relative ([string]$entry.relative) -Label 'game destination'
        if ([bool]$entry.existed_before) {
            if ((Get-Sha256 $dest) -ne ([string]$entry.before_sha256).ToLowerInvariant()) { throw "Rollback verification failed: $($entry.name)" }
        }
        elseif (Test-Path -LiteralPath $dest) {
            throw "Rollback expected file to be absent: $($entry.name)"
        }
    }
}

function Invoke-TransactionalInstall(
    [string]$Game,
    [string]$Candidate,
    [string]$State,
    [string]$Active,
    [System.Collections.IDictionary]$FileMap,
    [System.Collections.IDictionary]$CandidateShas,
    [string]$CandidateLabel,
    [string]$RepoBranch,
    [string]$RepoHead,
    [string]$ProofPath,
    [int]$FailureInjectionAfter = -1
) {
    $manifest = New-TransactionManifest -Game $Game -Candidate $Candidate -State $State -Active $Active -FileMap $FileMap -CandidateShas $CandidateShas -CandidateLabel $CandidateLabel -RepoBranch $RepoBranch -RepoHead $RepoHead -ProofPath $ProofPath
    try {
        $manifest.status = 'installing'
        Save-TransactionManifest -Manifest $manifest -Active $Active
        Install-TransactionFiles -Manifest $manifest -Game $Game -Candidate $Candidate -FailureInjectionAfter $FailureInjectionAfter
        $manifest.status = 'installed'
        $manifest.installed_utc = (Get-Date).ToUniversalTime().ToString('o')
        Save-TransactionManifest -Manifest $manifest -Active $Active
        return $manifest
    }
    catch {
        $installError = $_.Exception.Message
        try {
            Restore-State -Manifest $manifest -Game $Game -CheckInstalled $false -Force $true
            $manifest.status = 'rolled-back-after-install-failure'
            $manifest.rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
            Save-TransactionManifest -Manifest $manifest -Active $Active
        }
        catch {
            $rollbackError = $_.Exception.Message
            $manifest.status = 'rollback-failed-after-install-failure'
            Save-TransactionManifest -Manifest $manifest -Active $Active
            throw "Candidate 3 install failed: $installError`nAutomatic rollback also failed: $rollbackError`nDo not launch God of War until reviewed."
        }
        throw "Candidate 3 install failed and was automatically rolled back. Original error: $installError"
    }
}

if ($LibraryOnly) { return }

if ($Mode -eq 'Status') {
    Write-Host 'NORNIR_RUNTIME_CANDIDATE3_STATUS'
    Write-Host "  candidate proof: $archivedReport"
    Write-Host '  runtime proof state: OFFLINE_ONLY'
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
Assert-PathTopology -Game $GameRoot -Candidate $candidateRoot -State $stateRoot
$branch = Assert-Branch
Assert-TrackedTreeClean
Assert-GameClosed

if ($Mode -eq 'Install') {
    if (-not $ConfirmRuntimeTest) {
        throw 'Candidate 3 install is intentionally disarmed. Re-run with -ConfirmRuntimeTest only after reviewing the offline installer self-test and deciding to perform the controlled field test.'
    }
    if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
        $old = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
        if ($old.status -in @('backup-complete','installing','installed','rollback-failed-after-install-failure')) {
            throw "Active Candidate 3 transaction already exists with status '$($old.status)'. Resolve or roll it back first."
        }
    }

    $candidate = Assert-Candidate3
    Write-Host 'Re-verifying frozen Raven production immediately before Candidate 3 install...'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verification failed. Candidate 3 was not installed.' }

    $head = (& git -C $repo rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not determine Git HEAD.' }
    $manifest = Invoke-TransactionalInstall -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -FileMap $files -CandidateShas $candidate.shas -CandidateLabel 'nornir-runtime-candidate3' -RepoBranch $branch -RepoHead $head -ProofPath $archivedReport

    Write-Host ''
    Write-Host 'NORNIR_RUNTIME_CANDIDATE3_INSTALLED'
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host '  Candidate 3 offline proof verified: true'
    Write-Host '  ten files installed and SHA-verified: true'
    Write-Host '  all pre-install backups completed before first game write: true'
    Write-Host '  saves/progression/marker state written by installer: false'
    Write-Host '  God of War launched by installer: false'
    Write-Host "  manifest: $(Join-Path ([string]$manifest.transaction_root) 'manifest.json')"
    exit 0
}

if ($Mode -eq 'Rollback') {
    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) { throw 'No Candidate 3 transaction exists.' }
    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    if ($manifest.candidate -ne 'nornir-runtime-candidate3') { throw "Active transaction belongs to a different candidate: $($manifest.candidate)" }
    if ($manifest.status -ne 'installed' -and -not $ForceRollback) {
        throw "Candidate 3 transaction status is '$($manifest.status)', not 'installed'."
    }
    if ((Get-FullPath ([string]$manifest.game_root)) -ne (Get-FullPath $GameRoot)) { throw "Transaction belongs to a different game root: $($manifest.game_root)" }

    Restore-State -Manifest $manifest -Game $GameRoot -CheckInstalled $true -Force ([bool]$ForceRollback)
    $manifest.status = 'rolled-back'
    $manifest.rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
    Save-TransactionManifest -Manifest $manifest -Active $activeManifest

    Write-Host 'Re-verifying frozen Raven production after Candidate 3 rollback...'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Rollback restored files, but Raven production verification failed. Do not launch God of War until reviewed.' }

    Write-Host ''
    Write-Host 'NORNIR_RUNTIME_CANDIDATE3_ROLLED_BACK'
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host '  exact pre-install state restored: true'
    Write-Host '  Raven production verifier passed: true'
    Write-Host '  saves/progression/marker state touched by rollback: false'
    exit 0
}
