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

function Assert-NoReparsePoint([string]$Path, [string]$Label) {
    $full = Get-FullPath $Path
    $volume = [IO.Path]::GetPathRoot($full)
    $current = $volume
    $tail = $full.Substring($volume.Length)
    foreach ($segment in @($tail -split '[\\/]' | Where-Object { $_ -ne '' })) {
        $current = Join-Path $current $segment
        if (-not (Test-Path -LiteralPath $current)) { break }
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "$Label contains a reparse point: $current"
        }
    }
}

function Test-PathWithin([string]$Parent, [string]$Child) {
    $parentFull = (Get-FullPath $Parent).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $childFull = Get-FullPath $Child
    if ($childFull.Equals($parentFull, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    $prefix = $parentFull + [IO.Path]::DirectorySeparatorChar
    return $childFull.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)
}

function Get-SafeRelativePath([string]$Root, [string]$Path, [string]$Label) {
    $rootFull = (Get-FullPath $Root).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $pathFull = Get-FullPath $Path
    if (-not (Test-PathWithin -Parent $rootFull -Child $pathFull) -or $pathFull.Equals($rootFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label is not a child of its root: $Path"
    }
    return $pathFull.Substring($rootFull.Length + 1).Replace('\','/')
}

function Resolve-SafeChildPath([string]$Root, [string]$Relative, [string]$Label) {
    if ([IO.Path]::IsPathRooted($Relative)) { throw "$Label must be relative: $Relative" }
    $full = Get-FullPath (Join-Path $Root $Relative)
    if (-not (Test-PathWithin -Parent $Root -Child $full)) { throw "$Label escapes root: $Relative" }
    Assert-NoReparsePoint -Path $Root -Label "$Label root"
    Assert-NoReparsePoint -Path $full -Label $Label
    return $full
}

function Assert-PathTopology([string]$Game, [string]$Candidate, [string]$State) {
    $gameFull = Get-FullPath $Game
    $candidateFull = Get-FullPath $Candidate
    $stateFull = Get-FullPath $State
    $repoFull = Get-FullPath $repo
    $buildFull = Get-FullPath (Join-Path $repoFull 'build')
    if (-not (Test-PathWithin -Parent $buildFull -Child $candidateFull)) { throw 'Candidate root must stay inside the repository build tree.' }
    if (-not (Test-PathWithin -Parent $buildFull -Child $stateFull)) { throw 'Transaction state must stay inside the repository build tree.' }
    foreach ($pair in @(
        @('installed game', $gameFull, 'Candidate 3 output', $candidateFull),
        @('installed game', $gameFull, 'transaction state', $stateFull),
        @('Candidate 3 output', $candidateFull, 'transaction state', $stateFull)
    )) {
        if ((Test-PathWithin -Parent $pair[1] -Child $pair[3]) -or (Test-PathWithin -Parent $pair[3] -Child $pair[1])) {
            throw "$($pair[0]) and $($pair[2]) paths must not overlap."
        }
    }
    Assert-NoReparsePoint -Path $gameFull -Label 'installed game root'
    Assert-NoReparsePoint -Path $candidateFull -Label 'Candidate 3 output root'
    Assert-NoReparsePoint -Path $stateFull -Label 'transaction state root'
}

function Assert-GameClosed([string]$Game) {
    $gameFull = if ([string]::IsNullOrWhiteSpace($Game)) { $null } else { Get-FullPath $Game }
    foreach ($process in @(Get-Process -ErrorAction SilentlyContinue)) {
        if ($process.ProcessName -in @('GoW','GodOfWar')) { throw 'Close God of War first.' }
        if ($null -eq $gameFull) { continue }
        try {
            $processPath = [string]$process.Path
            if (-not [string]::IsNullOrWhiteSpace($processPath) -and (Test-PathWithin -Parent $gameFull -Child $processPath)) {
                throw "Close process running from the God of War root first: $($process.ProcessName)"
            }
        }
        catch [System.Management.Automation.PropertyNotFoundException] {}
        catch [System.ComponentModel.Win32Exception] {}
    }
}

function Assert-GameRootIdentity([string]$Game) {
    $executable = Resolve-SafeChildPath -Root $Game -Relative 'GoW.exe' -Label 'God of War executable'
    if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { throw "God of War executable not found under game root: $executable" }
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

function Get-RepoHead {
    $head = (& git -C $repo rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-fA-F]{40}$') { throw 'Could not determine Git HEAD.' }
    return $head.ToLowerInvariant()
}

function Assert-RepoHead([string]$ExpectedHead) {
    $actualHead = Get-RepoHead
    if ($actualHead -ne $ExpectedHead.ToLowerInvariant()) { throw "Git HEAD changed during Candidate 3 transaction setup: $actualHead" }
}

function Assert-RavenProduction([string]$Game) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $Game | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verification failed. Candidate 3 was not installed.' }
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
    Assert-NoReparsePoint -Path $Source -Label 'copy source'
    Assert-NoReparsePoint -Path (Split-Path $Destination -Parent) -Label 'copy destination parent'
    Assert-NoReparsePoint -Path $Destination -Label 'copy destination'
    $temp = "$Destination.completionist-tmp-$([Guid]::NewGuid().ToString('N'))"
    try {
        Copy-Item -LiteralPath $Source -Destination $temp -Force
        if ((Get-Sha256 $temp) -ne $ExpectedSha.ToLowerInvariant()) { throw "Temporary SHA mismatch: $Destination" }
        Assert-NoReparsePoint -Path (Split-Path $Destination -Parent) -Label 'copy destination parent'
        Assert-NoReparsePoint -Path $Destination -Label 'copy destination'
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

function Get-ApprovedCandidate3Shas([object]$Proof) {
    Assert-ProofObject $Proof
    $approvedShas = [ordered]@{}
    foreach ($name in $files.Keys) {
        $relative = ([string]$files[$name]).Replace('\','/')
        $property = $Proof.candidate3.files.PSObject.Properties[$relative]
        if ($null -eq $property) { throw "Missing Candidate 3 proof entry: $relative" }
        $sha = ([string]$property.Value.sha256).ToLowerInvariant()
        if ($sha -notmatch '^[0-9a-f]{64}$') { throw "Invalid Candidate 3 proof SHA: $relative" }
        $approvedShas[$name] = $sha
    }
    if ($approvedShas['r_ui.wad'] -ne $expectedCandidateWad -or $approvedShas['r_ui.wad'] -eq $retiredCandidate2Wad) {
        throw 'Candidate 3 proof does not pin the approved Candidate 3 WAD.'
    }
    return $approvedShas
}

function Assert-Candidate3 {
    foreach ($required in @($candidateRoot, $archivedReport, $verifyRaven)) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Missing Candidate 3 prerequisite: $required`nRe-run .\tools\v0.10.4\run-collectible-framework-offline.ps1 first."
        }
    }

    $proof = Get-Content -LiteralPath $archivedReport -Raw | ConvertFrom-Json
    $candidateShas = Get-ApprovedCandidate3Shas $proof

    $diskFiles = @(Get-ChildItem -LiteralPath $candidateRoot -Recurse -File | ForEach-Object {
        Get-SafeRelativePath -Root $candidateRoot -Path $_.FullName -Label 'candidate file'
    } | Sort-Object)
    $approved = @($files.Values | ForEach-Object { ([string]$_).Replace('\','/') } | Sort-Object)
    if (($diskFiles -join "`n") -ne ($approved -join "`n")) { throw 'Candidate 3 output root contains a missing or unexpected file.' }

    foreach ($name in $files.Keys) {
        $relative = ([string]$files[$name]).Replace('\','/')
        $expectedSha = [string]$candidateShas[$name]
        $source = Resolve-SafeChildPath -Root $candidateRoot -Relative $relative -Label 'candidate source'
        if ((Get-Sha256 $source) -ne $expectedSha) { throw "Candidate 3 file SHA mismatch: $name" }
    }
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
    $transactionRoot = Resolve-SafeChildPath -Root $State -Relative ('transactions/' + $transactionId) -Label 'transaction root'
    $backupRoot = Resolve-SafeChildPath -Root $transactionRoot -Relative 'backup/game-root' -Label 'backup root'
    $transactionManifest = Resolve-SafeChildPath -Root $transactionRoot -Relative 'manifest.json' -Label 'transaction manifest'
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
            Copy-Verified -Source $dest -Destination $backup -ExpectedSha $beforeSha
        }

        $entries += [ordered]@{
            name = $name
            relative = $relative
            candidate_sha256 = $candidateSha
            existed_before = [bool]$existed
            before_sha256 = $beforeSha
            backup_relative = $backupRelative
            write_state = 'pending'
        }
    }

    $manifest = [ordered]@{
        schema = 2
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

function Assert-RollbackStatus([string]$Status, [bool]$Force) {
    $recoverable = @('backup-complete','installing','installed','rolling-back','rolling-back-after-install-failure','rollback-failed-after-install-failure')
    $terminal = @('rolled-back','rolled-back-after-install-failure')
    if ($Status -in $terminal) { throw "Candidate 3 transaction status '$Status' is terminal and cannot be rolled back again." }
    if ($Status -notin $recoverable) { throw "Unknown Candidate 3 transaction status: '$Status'." }
    if ($Status -ne 'installed' -and -not $Force) {
        throw "Candidate 3 transaction status is '$Status', not 'installed'. Use -ForceRollback only after review."
    }
}

function Assert-TransactionManifest(
    [object]$Manifest,
    [string]$Game,
    [string]$Candidate,
    [string]$State,
    [string]$ProofPath,
    [System.Collections.IDictionary]$FileMap,
    [System.Collections.IDictionary]$CandidateShas,
    [string]$CandidateLabel,
    [string]$RepoBranch
) {
    if ([int]$Manifest.schema -ne 2) { throw 'Candidate 3 transaction manifest schema must be 2.' }
    if ([string]$Manifest.candidate -ne $CandidateLabel) { throw "Active transaction belongs to a different candidate: $($Manifest.candidate)" }
    if ([string]$Manifest.repo_branch -ne $RepoBranch) { throw 'Candidate 3 transaction branch does not match.' }
    if ([string]$Manifest.transaction_id -notmatch '^\d{8}T\d{6}Z-[0-9a-f]{8}$') { throw 'Candidate 3 transaction ID is invalid.' }
    if ((Get-FullPath ([string]$Manifest.game_root)) -ne (Get-FullPath $Game)) { throw "Transaction belongs to a different game root: $($Manifest.game_root)" }
    if ((Get-FullPath ([string]$Manifest.candidate_root)) -ne (Get-FullPath $Candidate)) { throw 'Candidate 3 transaction candidate root does not match.' }
    if ([string]$Manifest.archived_proof -ne $ProofPath) { throw 'Candidate 3 transaction proof path does not match.' }
    if ([string]$Manifest.status -notin @('backup-complete','installing','installed','rolling-back','rolling-back-after-install-failure','rollback-failed-after-install-failure','rolled-back','rolled-back-after-install-failure')) {
        throw "Unknown Candidate 3 transaction status: '$($Manifest.status)'."
    }

    $expectedTransactionRoot = Get-FullPath (Join-Path $State ('transactions\' + [string]$Manifest.transaction_id))
    $actualTransactionRoot = Get-FullPath ([string]$Manifest.transaction_root)
    if ($actualTransactionRoot -ne $expectedTransactionRoot -or -not (Test-PathWithin -Parent $State -Child $actualTransactionRoot)) {
        throw 'Candidate 3 transaction root does not match its state root and transaction ID.'
    }
    Assert-NoReparsePoint -Path $actualTransactionRoot -Label 'transaction root'

    $entries = @($Manifest.entries)
    if ($entries.Count -ne @($FileMap.Keys).Count) { throw 'Candidate 3 transaction must contain exactly ten entries.' }
    for ($index = 0; $index -lt $entries.Count; $index++) {
        $entry = $entries[$index]
        $name = [string]@($FileMap.Keys)[$index]
        $relative = ([string]$FileMap[$name]).Replace('\','/')
        if ([string]$entry.name -ne $name -or ([string]$entry.relative).Replace('\','/') -ne $relative) {
            throw "Candidate 3 transaction entry order or path changed at index $index."
        }
        $expectedCandidateSha = ([string]$CandidateShas[$name]).ToLowerInvariant()
        if ([string]$entry.candidate_sha256 -ne $expectedCandidateSha) { throw "Candidate 3 transaction SHA changed: $name" }
        if ([string]$entry.write_state -notin @('pending','write-started','installed','restored')) { throw "Invalid write state: $name" }

        if ([bool]$entry.existed_before) {
            if ([string]$entry.before_sha256 -notmatch '^[0-9a-f]{64}$') { throw "Invalid pre-install SHA: $name" }
            $expectedBackup = 'backup/game-root/' + $relative
            if (([string]$entry.backup_relative).Replace('\','/') -ne $expectedBackup) { throw "Invalid backup path: $name" }
            [void](Resolve-SafeChildPath -Root $actualTransactionRoot -Relative $expectedBackup -Label 'backup path')
        }
        else {
            if ($null -ne $entry.before_sha256 -or $null -ne $entry.backup_relative) { throw "Unexpected backup metadata for new file: $name" }
        }
    }

    $states = @($entries | ForEach-Object { [string]$_.write_state })
    if ([string]$Manifest.status -eq 'backup-complete' -and @($states | Where-Object { $_ -ne 'pending' }).Count -ne 0) {
        throw 'Backup-complete transaction contains a written entry.'
    }
    if ([string]$Manifest.status -eq 'installed' -and @($states | Where-Object { $_ -ne 'installed' }).Count -ne 0) {
        throw 'Installed transaction does not mark every entry installed.'
    }
    if ([string]$Manifest.status -in @('rolled-back','rolled-back-after-install-failure') -and @($states | Where-Object { $_ -notin @('pending','restored') }).Count -ne 0) {
        throw 'Rolled-back transaction contains an unrestored written entry.'
    }
}

function Get-ValidatedActiveTransaction(
    [string]$Active,
    [string]$Game,
    [string]$Candidate,
    [string]$State,
    [string]$ProofPath,
    [System.Collections.IDictionary]$FileMap,
    [System.Collections.IDictionary]$CandidateShas,
    [string]$CandidateLabel,
    [string]$RepoBranch
) {
    $activeValue = Get-Content -LiteralPath $Active -Raw | ConvertFrom-Json
    Assert-TransactionManifest -Manifest $activeValue -Game $Game -Candidate $Candidate -State $State -ProofPath $ProofPath -FileMap $FileMap -CandidateShas $CandidateShas -CandidateLabel $CandidateLabel -RepoBranch $RepoBranch
    $transactionPath = Resolve-SafeChildPath -Root ([string]$activeValue.transaction_root) -Relative 'manifest.json' -Label 'transaction manifest'
    $transactionValue = Get-Content -LiteralPath $transactionPath -Raw | ConvertFrom-Json
    Assert-TransactionManifest -Manifest $transactionValue -Game $Game -Candidate $Candidate -State $State -ProofPath $ProofPath -FileMap $FileMap -CandidateShas $CandidateShas -CandidateLabel $CandidateLabel -RepoBranch $RepoBranch
    if ([string]$transactionValue.transaction_id -ne [string]$activeValue.transaction_id) { throw 'Active and transaction manifest IDs differ.' }
    return $transactionValue
}

function Install-TransactionFiles(
    [object]$Manifest,
    [string]$Game,
    [string]$Candidate,
    [string]$Active,
    [scriptblock]$WriteGuard,
    [int]$FailureInjectionAfter = -1
) {
    $written = 0
    foreach ($entry in @($Manifest.entries)) {
        $source = Resolve-SafeChildPath -Root $Candidate -Relative ([string]$entry.relative) -Label 'candidate source'
        $dest = Resolve-SafeChildPath -Root $Game -Relative ([string]$entry.relative) -Label 'game destination'
        $entry.write_state = 'write-started'
        Save-TransactionManifest -Manifest $Manifest -Active $Active
        if ($null -ne $WriteGuard) { & $WriteGuard }
        Copy-Verified -Source $source -Destination $dest -ExpectedSha ([string]$entry.candidate_sha256)
        $entry.write_state = 'installed'
        Save-TransactionManifest -Manifest $Manifest -Active $Active
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

function Restore-State(
    [object]$Manifest,
    [string]$Game,
    [string]$Candidate,
    [string]$State,
    [string]$Active,
    [string]$ProofPath,
    [System.Collections.IDictionary]$FileMap,
    [System.Collections.IDictionary]$CandidateShas,
    [string]$CandidateLabel,
    [string]$RepoBranch,
    [bool]$CheckInstalled,
    [bool]$Force,
    [scriptblock]$WriteGuard
) {
    Assert-TransactionManifest -Manifest $Manifest -Game $Game -Candidate $Candidate -State $State -ProofPath $ProofPath -FileMap $FileMap -CandidateShas $CandidateShas -CandidateLabel $CandidateLabel -RepoBranch $RepoBranch
    $actionEntries = @($Manifest.entries | Where-Object { [string]$_.write_state -in @('write-started','installed') })

    if ($CheckInstalled -and -not $Force) {
        foreach ($entry in $actionEntries) {
            if ([string]$entry.write_state -ne 'installed') { throw "Transaction write state is uncertain before rollback: $($entry.name)" }
            $dest = Resolve-SafeChildPath -Root $Game -Relative ([string]$entry.relative) -Label 'game destination'
            if (-not (Test-Path -LiteralPath $dest -PathType Leaf)) { throw "Installed file missing before rollback: $($entry.name)" }
            if ((Get-Sha256 $dest) -ne ([string]$entry.candidate_sha256).ToLowerInvariant()) {
                throw "Installed file changed since Candidate 3 install: $($entry.name). Use -ForceRollback only after reviewing it."
            }
        }
    }

    # Check every needed backup before first rollback write.
    foreach ($entry in $actionEntries) {
        if (-not [bool]$entry.existed_before) { continue }
        $backup = Resolve-SafeChildPath -Root ([string]$Manifest.transaction_root) -Relative ([string]$entry.backup_relative) -Label 'backup path'
        $beforeSha = ([string]$entry.before_sha256).ToLowerInvariant()
        if ((Get-Sha256 $backup) -ne $beforeSha) { throw "Backup SHA mismatch: $($entry.name)" }
    }

    if ([string]$Manifest.status -in @('rolled-back','rolled-back-after-install-failure')) {
        throw "Candidate 3 transaction status '$($Manifest.status)' is terminal and cannot be rolled back again."
    }
    if ([string]$Manifest.status -notin @('rolling-back','rolling-back-after-install-failure')) {
        $Manifest.status = if ([string]$Manifest.status -eq 'installed') { 'rolling-back' } else { 'rolling-back-after-install-failure' }
        Save-TransactionManifest -Manifest $Manifest -Active $Active
    }

    $reverse = @($actionEntries)
    [array]::Reverse($reverse)
    foreach ($entry in $reverse) {
        $dest = Resolve-SafeChildPath -Root $Game -Relative ([string]$entry.relative) -Label 'game destination'
        $currentSha = if (Test-Path -LiteralPath $dest -PathType Leaf) { Get-Sha256 $dest } else { $null }
        $candidateSha = ([string]$entry.candidate_sha256).ToLowerInvariant()
        if ([bool]$entry.existed_before) {
            $backup = Resolve-SafeChildPath -Root ([string]$Manifest.transaction_root) -Relative ([string]$entry.backup_relative) -Label 'backup path'
            $beforeSha = ([string]$entry.before_sha256).ToLowerInvariant()
            if ($currentSha -ne $beforeSha) {
                if ($null -ne $currentSha -and $currentSha -ne $candidateSha -and (-not $Force -or [string]$entry.write_state -ne 'installed')) {
                    throw "Destination changed during uncertain rollback state: $($entry.name)"
                }
                if ($null -ne $WriteGuard) { & $WriteGuard }
                Copy-Verified -Source $backup -Destination $dest -ExpectedSha $beforeSha
            }
        }
        else {
            if ($null -ne $currentSha) {
                if ($currentSha -ne $candidateSha -and (-not $Force -or [string]$entry.write_state -ne 'installed')) {
                    throw "Refusing to remove non-Candidate 3 file during uncertain rollback state: $($entry.name)"
                }
                if ($null -ne $WriteGuard) { & $WriteGuard }
                Assert-NoReparsePoint -Path $dest -Label 'rollback destination'
                Remove-Item -LiteralPath $dest -Force
                if (Test-Path -LiteralPath $dest) { throw "Could not remove newly-created file: $($entry.name)" }
            }
        }
        $entry.write_state = 'restored'
        Save-TransactionManifest -Manifest $Manifest -Active $Active
    }

    foreach ($entry in $actionEntries) {
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
    [scriptblock]$PreWriteValidation,
    [scriptblock]$WriteGuard,
    [int]$FailureInjectionAfter = -1
) {
    $manifest = New-TransactionManifest -Game $Game -Candidate $Candidate -State $State -Active $Active -FileMap $FileMap -CandidateShas $CandidateShas -CandidateLabel $CandidateLabel -RepoBranch $RepoBranch -RepoHead $RepoHead -ProofPath $ProofPath
    try {
        if ($null -ne $PreWriteValidation) { & $PreWriteValidation }
        $manifest.status = 'installing'
        Save-TransactionManifest -Manifest $manifest -Active $Active
        Install-TransactionFiles -Manifest $manifest -Game $Game -Candidate $Candidate -Active $Active -WriteGuard $WriteGuard -FailureInjectionAfter $FailureInjectionAfter
        $manifest.status = 'installed'
        $manifest.installed_utc = (Get-Date).ToUniversalTime().ToString('o')
        Save-TransactionManifest -Manifest $manifest -Active $Active
        return $manifest
    }
    catch {
        $installError = $_.Exception.Message
        try {
            Restore-State -Manifest $manifest -Game $Game -Candidate $Candidate -State $State -Active $Active -ProofPath $ProofPath -FileMap $FileMap -CandidateShas $CandidateShas -CandidateLabel $CandidateLabel -RepoBranch $RepoBranch -CheckInstalled $false -Force $false -WriteGuard $WriteGuard
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
Assert-GameRootIdentity -Game $GameRoot
$branch = Assert-Branch
Assert-TrackedTreeClean
Assert-GameClosed -Game $GameRoot
$operationHead = Get-RepoHead

if ($Mode -eq 'Install') {
    if (-not $ConfirmRuntimeTest) {
        throw 'Candidate 3 install is intentionally disarmed. Re-run with -ConfirmRuntimeTest only after reviewing the offline installer self-test and deciding to perform the controlled field test.'
    }

    $candidate = Assert-Candidate3
    if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
        $old = Get-ValidatedActiveTransaction -Active $activeManifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -ProofPath $archivedReport -FileMap $files -CandidateShas $candidate.shas -CandidateLabel 'nornir-runtime-candidate3' -RepoBranch $branch
        if ([string]$old.status -notin @('rolled-back','rolled-back-after-install-failure')) { throw "Active Candidate 3 transaction already exists with status '$($old.status)'. Resolve or roll it back first." }
    }

    Write-Host 'Re-verifying frozen Raven production immediately before Candidate 3 install...'
    Assert-RavenProduction -Game $GameRoot

    $preWriteValidation = {
        [void](Assert-Branch)
        Assert-RepoHead -ExpectedHead $operationHead
        Assert-TrackedTreeClean
        Assert-GameClosed -Game $GameRoot
        Write-Host 'Re-verifying frozen Raven after backup and immediately before first Candidate 3 write...'
        Assert-RavenProduction -Game $GameRoot
        Assert-GameClosed -Game $GameRoot
    }
    $writeGuard = {
        Assert-GameClosed -Game $GameRoot
        Assert-RepoHead -ExpectedHead $operationHead
        Assert-TrackedTreeClean
    }
    $manifest = Invoke-TransactionalInstall -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -FileMap $files -CandidateShas $candidate.shas -CandidateLabel 'nornir-runtime-candidate3' -RepoBranch $branch -RepoHead $operationHead -ProofPath $archivedReport -PreWriteValidation $preWriteValidation -WriteGuard $writeGuard

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
    $proof = Get-Content -LiteralPath $archivedReport -Raw | ConvertFrom-Json
    $approvedShas = Get-ApprovedCandidate3Shas $proof
    $manifest = Get-ValidatedActiveTransaction -Active $activeManifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -ProofPath $archivedReport -FileMap $files -CandidateShas $approvedShas -CandidateLabel 'nornir-runtime-candidate3' -RepoBranch $branch
    Assert-RollbackStatus -Status ([string]$manifest.status) -Force ([bool]$ForceRollback)
    Assert-GameClosed -Game $GameRoot
    $writeGuard = {
        Assert-GameClosed -Game $GameRoot
        Assert-RepoHead -ExpectedHead $operationHead
        Assert-TrackedTreeClean
    }
    Restore-State -Manifest $manifest -Game $GameRoot -Candidate $candidateRoot -State $stateRoot -Active $activeManifest -ProofPath $archivedReport -FileMap $files -CandidateShas $approvedShas -CandidateLabel 'nornir-runtime-candidate3' -RepoBranch $branch -CheckInstalled $true -Force ([bool]$ForceRollback) -WriteGuard $writeGuard
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
