param(
    [ValidateSet('Install','Rollback','Status')]
    [string]$Mode = 'Status',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$ForceRollback
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedBranch = 'codex/v104-raven-production'
$runtimeState = Join-Path $repo 'build\v0.10.4-nornir-runtime'
$activeManifest = Join-Path $runtimeState 'active.json'
$lifecycleState = Join-Path $repo 'build\v0.10.4-nornir-lifecycle\offline'
$candidateRoot = Join-Path $lifecycleState 'candidate\game-root'
$lifecycleReport = Join-Path $lifecycleState 'nornir-lifecycle-offline.json'
$archivedLifecycle = Join-Path $repo 'archive\field-logs\completionist-v104-nornir-lifecycle-offline-success.json'
$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'

$expected = [ordered]@{
    'r_ui.wad' = 'exec\wad\pc_le\r_ui.wad'
    'wad_r_ui.dcb' = 'exec\dc\pc_le\wad_r_ui.dcb'
    'wad_r_perm.dcb' = 'exec\dc\pc_le\wad_r_perm.dcb'
    'mapmaster.dcb' = 'exec\dc\pc_le\mapmaster.dcb'
    'mapcoords.dcb' = 'exec\dc\pc_le\mapcoords.dcb'
    'compassgraph.dcb' = 'exec\dc\pc_le\compassgraph.dcb'
    'mapmenu.lua' = 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
    'mainhud.lua' = 'mods\lua\gameart\ui\scripts\hud\mainhud.lua'
    'interact_chest_runic.lua' = 'mods\lua\gameart\scripts\levels\gameplaymodules\progression\interact_chest_runic.lua'
    'interact_chest_standard.lua' = 'mods\lua\gameart\scripts\levels\gameplaymodules\progression\interact_chest_standard.lua'
}

function Assert-GodOfWarClosed {
    if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before changing the Nornir runtime transaction.' }
    if (Get-Process -Name GodOfWar -ErrorAction SilentlyContinue) { throw 'Close God of War before changing the Nornir runtime transaction.' }
}

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "File missing for SHA256: $Path" }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Write-JsonAtomic([object]$Object, [string]$Path) {
    $parent = Split-Path $Path -Parent
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $tmp = $Path + '.tmp-' + [Guid]::NewGuid().ToString('N')
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    try {
        $json = $Object | ConvertTo-Json -Depth 20
        [IO.File]::WriteAllText($tmp, $json + [Environment]::NewLine, $utf8NoBom)
        Move-Item -LiteralPath $tmp -Destination $Path -Force
    }
    finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}

function Get-ReportEntry([object]$Proof, [string]$Name) {
    if ($Name -in @('r_ui.wad','wad_r_ui.dcb','wad_r_perm.dcb','mapmaster.dcb','mapcoords.dcb','compassgraph.dcb')) {
        $property = $Proof.candidate.six_binary_files.PSObject.Properties[$Name]
    }
    else {
        $property = $Proof.candidate.four_lua_files.PSObject.Properties[$Name]
    }
    if ($null -eq $property) { throw "Lifecycle report entry missing: $Name" }
    return $property.Value
}

function Assert-LifecycleCandidate {
    foreach ($required in @($candidateRoot, $lifecycleReport, $archivedLifecycle, $verifyRaven)) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Missing passing lifecycle component: $required`nRe-run tools\v0.10.4\run-nornir-lifecycle-offline-v2.ps1 first."
        }
    }

    $proof = Get-Content -LiteralPath $lifecycleReport -Raw | ConvertFrom-Json
    if ($proof.result -ne 'OFFLINE_NORNIR_LIFECYCLE_BUILT_AND_REPARSED' -or
        -not $proof.candidate.ten_file_candidate_complete -or
        -not $proof.source_game_and_loader_files_unchanged -or
        -not $proof.proof.frozen_raven_mapmenu_is_exact_prefix_of_candidate -or
        -not $proof.proof.old_synthetic_nornir_map_hud_path_retired -or
        -not $proof.proof.native_nornir_single_target_add_replace_remove_present -or
        -not $proof.proof.real_stock_nornir_lifecycle_bridge_present -or
        -not $proof.proof.all_six_binary_vertical_slice_files_copied_unchanged -or
        -not $proof.proof.no_save_progression_or_marker_state_mutation_authored -or
        $proof.runtime_ready -or
        -not $proof.ready_for_reversible_runtime_installer_gate -or
        $proof.safety.game_files_written -or
        $proof.safety.runtime_install_performed -or
        $proof.safety.save_state_written -or
        $proof.safety.progression_state_written -or
        $proof.safety.marker_state_written -or
        $proof.safety.raven_production_files_changed) {
        throw 'Nornir lifecycle report is not an approved passing offline candidate.'
    }

    if ($proof.candidate.marker -ne 'Completionist_V104_Veithurgard_NornirChest_01' -or
        $proof.candidate.marker_id -ne '381B067F07254A25' -or
        $proof.candidate.compass_class.name -ne 'CompletionistNornirChest' -or
        $proof.candidate.compass_class.uid -ne '8D5A770E0C4272CE' -or
        $proof.candidate.map_visual.hash -ne 'E14C66C3B90633E0' -or
        $proof.candidate.hud_visual.hash -ne '7DDC11175EBD1E94' -or
        $proof.candidate.hud_visual.capacity -ne 2 -or
        $proof.candidate.inworld_carrier.uid -ne '32BBE7E267644D93') {
        throw 'Nornir lifecycle candidate identities changed.'
    }

    if (-not $proof.lifecycle_contract.runic_parent_challengeComplete_is_observed -or
        -not $proof.lifecycle_contract.runic_parent_restored_state_is_published_on_OnStart -or
        -not $proof.lifecycle_contract.actual_runic_loot_chest_OPENED_is_authoritative_collectible_completion -or
        -not $proof.lifecycle_contract.restored_opened_state_is_published_on_standard_chest_OnStart -or
        -not $proof.lifecycle_contract.challengeComplete_without_opened_keeps_parent_marker_visible -or
        -not $proof.lifecycle_contract.opened_suppresses_map_marker -or
        -not $proof.lifecycle_contract.opened_removes_active_native_compass_target -or
        $proof.lifecycle_contract.synthetic_progression_writes) {
        throw 'Nornir lifecycle semantics no longer match the approved completion contract.'
    }

    $archived = Get-Content -LiteralPath $archivedLifecycle -Raw | ConvertFrom-Json
    if ($archived.result -ne 'NORNIR_LIFECYCLE_OFFLINE_GATE_PASSED' -or
        $archived.candidate.marker_id -ne '381B067F07254A25' -or
        -not $archived.proof.raven_production_reverified_before_and_after -or
        $archived.proof.game_files_written -or
        $archived.proof.runtime_install_performed) {
        throw 'Archived lifecycle success proof does not match the passing local candidate.'
    }

    foreach ($name in $expected.Keys) {
        $source = Join-Path $candidateRoot $expected[$name]
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Ten-file candidate missing: $name" }
        $entry = Get-ReportEntry -Proof $proof -Name $name
        $expectedSha = ([string]$entry.sha256).ToLowerInvariant()
        $actualSha = Get-Sha256 $source
        if ($actualSha -ne $expectedSha) { throw "Ten-file candidate SHA mismatch: $name" }
    }

    return $proof
}

function Copy-VerifiedFile([string]$Source, [string]$Destination, [string]$ExpectedSha) {
    $parent = Split-Path $Destination -Parent
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $tmp = $Destination + '.completionist-tmp-' + [Guid]::NewGuid().ToString('N')
    try {
        Copy-Item -LiteralPath $Source -Destination $tmp -Force
        if ((Get-Sha256 $tmp) -ne $ExpectedSha) { throw "Temporary copy SHA mismatch: $Destination" }
        Move-Item -LiteralPath $tmp -Destination $Destination -Force
        if ((Get-Sha256 $Destination) -ne $ExpectedSha) { throw "Installed file SHA mismatch: $Destination" }
    }
    finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
}

function Restore-Transaction([object]$Manifest, [string]$TransactionRoot, [bool]$RequireInstalledCandidate, [bool]$Force) {
    Assert-GodOfWarClosed

    if ($RequireInstalledCandidate -and -not $Force) {
        foreach ($entry in @($Manifest.entries)) {
            $dest = Join-Path $GameRoot ([string]$entry.relative)
            if (-not (Test-Path -LiteralPath $dest -PathType Leaf)) {
                throw "Rollback safety check: installed destination missing: $($entry.name). Use -ForceRollback only after reviewing the file state."
            }
            $current = Get-Sha256 $dest
            if ($current -ne ([string]$entry.candidate_sha256).ToLowerInvariant()) {
                throw "Rollback safety check: destination changed since install: $($entry.name). Use -ForceRollback only if you intend to discard that change."
            }
        }
    }

    $entries = @($Manifest.entries)
    [array]::Reverse($entries)
    foreach ($entry in $entries) {
        $dest = Join-Path $GameRoot ([string]$entry.relative)
        if ([bool]$entry.existed_before) {
            $backup = Join-Path $TransactionRoot ([string]$entry.backup_relative)
            if (-not (Test-Path -LiteralPath $backup -PathType Leaf)) { throw "Rollback backup missing: $backup" }
            $beforeSha = ([string]$entry.before_sha256).ToLowerInvariant()
            if ((Get-Sha256 $backup) -ne $beforeSha) { throw "Rollback backup SHA mismatch: $($entry.name)" }
            Copy-VerifiedFile -Source $backup -Destination $dest -ExpectedSha $beforeSha
        }
        else {
            Remove-Item -LiteralPath $dest -Force -ErrorAction SilentlyContinue
            if (Test-Path -LiteralPath $dest) { throw "Rollback could not remove newly-created file: $dest" }
        }
    }

    foreach ($entry in @($Manifest.entries)) {
        $dest = Join-Path $GameRoot ([string]$entry.relative)
        if ([bool]$entry.existed_before) {
            if ((Get-Sha256 $dest) -ne ([string]$entry.before_sha256).ToLowerInvariant()) {
                throw "Rollback final SHA mismatch: $($entry.name)"
            }
        }
        elseif (Test-Path -LiteralPath $dest) {
            throw "Rollback final state mismatch, file should be absent: $($entry.name)"
        }
    }
}

if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

if ($Mode -eq 'Status') {
    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) {
        Write-Host 'NORNIR_RUNTIME_TRANSACTION_STATUS'
        Write-Host '  active transaction: none'
        Write-Host '  game files changed by this installer: false/unknown (no transaction manifest exists)'
        exit 0
    }

    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    Write-Host 'NORNIR_RUNTIME_TRANSACTION_STATUS'
    Write-Host "  id: $($manifest.transaction_id)"
    Write-Host "  status: $($manifest.status)"
    Write-Host "  game root: $($manifest.game_root)"
    Write-Host "  files: $(@($manifest.entries).Count)"
    Write-Host "  transaction root: $($manifest.transaction_root)"
    exit 0
}

$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not determine current Git branch.' }
if ($branch -ne $expectedBranch) { throw "Expected branch '$expectedBranch', got '$branch'." }
Assert-GodOfWarClosed

if ($Mode -eq 'Install') {
    if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
        $previous = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
        if ($previous.status -in @('backup-complete','installing','installed')) {
            throw "An active Nornir runtime transaction already exists with status '$($previous.status)'. Roll it back before installing again."
        }
    }

    $proof = Assert-LifecycleCandidate

    Write-Host 'Re-verifying frozen Raven production state immediately before runtime transaction...'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production state must pass before the Nornir runtime transaction.' }

    $transactionId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
    $transactionRoot = Join-Path $runtimeState ('transactions\' + $transactionId)
    $backupRoot = Join-Path $transactionRoot 'backup\game-root'
    $transactionManifest = Join-Path $transactionRoot 'manifest.json'
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

    $entries = @()
    foreach ($name in $expected.Keys) {
        $relative = $expected[$name]
        $source = Join-Path $candidateRoot $relative
        $dest = Join-Path $GameRoot $relative
        $reportEntry = Get-ReportEntry -Proof $proof -Name $name
        $candidateSha = ([string]$reportEntry.sha256).ToLowerInvariant()
        if ((Get-Sha256 $source) -ne $candidateSha) { throw "Candidate changed after lifecycle verification: $name" }

        $existed = Test-Path -LiteralPath $dest -PathType Leaf
        $beforeSha = $null
        $backupRelative = $null
        if ($existed) {
            $beforeSha = Get-Sha256 $dest
            $backupRelative = ('backup\game-root\' + $relative)
            $backup = Join-Path $transactionRoot $backupRelative
            New-Item -ItemType Directory -Force -Path (Split-Path $backup -Parent) | Out-Null
            Copy-Item -LiteralPath $dest -Destination $backup -Force
            if ((Get-Sha256 $backup) -ne $beforeSha) { throw "Backup SHA mismatch before install: $name" }
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
        transaction_id = $transactionId
        status = 'backup-complete'
        created_utc = (Get-Date).ToUniversalTime().ToString('o')
        installed_utc = $null
        rolled_back_utc = $null
        game_root = $GameRoot
        repo_branch = $branch
        repo_head = (& git -C $repo rev-parse HEAD).Trim()
        source_lifecycle_report = $lifecycleReport
        transaction_root = $transactionRoot
        candidate_marker = 'Completionist_V104_Veithurgard_NornirChest_01'
        candidate_marker_id = '381B067F07254A25'
        entries = $entries
        safety = [ordered]@{
            backup_complete_before_first_game_write = $true
            save_files_written_by_installer = $false
            progression_state_written_by_installer = $false
            marker_state_written_by_installer = $false
            automatic_rollback_on_install_failure = $true
        }
    }
    Write-JsonAtomic -Object $manifest -Path $transactionManifest
    Write-JsonAtomic -Object $manifest -Path $activeManifest

    try {
        $manifest.status = 'installing'
        Write-JsonAtomic -Object $manifest -Path $transactionManifest
        Write-JsonAtomic -Object $manifest -Path $activeManifest

        foreach ($entry in $entries) {
            $source = Join-Path $candidateRoot ([string]$entry.relative)
            $dest = Join-Path $GameRoot ([string]$entry.relative)
            Copy-VerifiedFile -Source $source -Destination $dest -ExpectedSha ([string]$entry.candidate_sha256)
            Write-Host ("  installed {0}" -f $entry.name)
        }

        foreach ($entry in $entries) {
            $dest = Join-Path $GameRoot ([string]$entry.relative)
            if ((Get-Sha256 $dest) -ne ([string]$entry.candidate_sha256).ToLowerInvariant()) {
                throw "Post-install ten-file SHA verification failed: $($entry.name)"
            }
        }

        $manifest.status = 'installed'
        $manifest.installed_utc = (Get-Date).ToUniversalTime().ToString('o')
        Write-JsonAtomic -Object $manifest -Path $transactionManifest
        Write-JsonAtomic -Object $manifest -Path $activeManifest
    }
    catch {
        $installError = $_.Exception.Message
        Write-Warning "Nornir runtime install failed: $installError"
        Write-Warning 'Attempting automatic restoration of the complete pre-install state...'
        try {
            Restore-Transaction -Manifest $manifest -TransactionRoot $transactionRoot -RequireInstalledCandidate $false -Force $true
            $manifest.status = 'rolled-back-after-install-failure'
            $manifest.rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
            Write-JsonAtomic -Object $manifest -Path $transactionManifest
            Write-JsonAtomic -Object $manifest -Path $activeManifest
            throw "Nornir runtime install failed and the complete pre-install file state was automatically restored. Original error: $installError"
        }
        catch {
            if ($manifest.status -ne 'rolled-back-after-install-failure') {
                $rollbackError = $_.Exception.Message
                $manifest.status = 'rollback-failed-after-install-failure'
                Write-JsonAtomic -Object $manifest -Path $transactionManifest
                Write-JsonAtomic -Object $manifest -Path $activeManifest
                throw "Nornir runtime install failed: $installError`nAutomatic rollback also failed: $rollbackError`nDo not launch God of War until the transaction is repaired."
            }
            throw
        }
    }

    Write-Host ''
    Write-Host 'NORNIR_RUNTIME_TRANSACTION_INSTALLED'
    Write-Host "  transaction: $transactionId"
    Write-Host '  ten candidate files installed and SHA-verified: true'
    Write-Host '  complete pre-install backups created before first game write: true'
    Write-Host '  Raven production baseline verified immediately before install: true'
    Write-Host '  saves/progression/marker state written by installer: false'
    Write-Host "  backup root: $backupRoot"
    Write-Host "  manifest: $transactionManifest"
    Write-Host ''
    Write-Host 'Rollback command (with God of War closed):'
    Write-Host '  powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\v0.10.4\nornir-runtime-transaction.ps1" -Mode Rollback'
    Write-Host ''
    Write-Host 'Do not test collectible completion on your master/public save. Use a disposable copy or a save you are prepared to restore.'
    exit 0
}

if ($Mode -eq 'Rollback') {
    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) { throw 'No Nornir runtime transaction manifest exists to roll back.' }
    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    if ($manifest.status -ne 'installed' -and -not $ForceRollback) {
        throw "Active transaction status is '$($manifest.status)', not 'installed'. Use -ForceRollback only after reviewing the transaction state."
    }
    if ([string]$manifest.game_root -ne $GameRoot) {
        throw "Transaction belongs to a different game root: $($manifest.game_root)"
    }

    $transactionRoot = [string]$manifest.transaction_root
    $transactionManifest = Join-Path $transactionRoot 'manifest.json'
    Restore-Transaction -Manifest $manifest -TransactionRoot $transactionRoot -RequireInstalledCandidate $true -Force ([bool]$ForceRollback)

    $manifest.status = 'rolled-back'
    $manifest.rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
    Write-JsonAtomic -Object $manifest -Path $transactionManifest
    Write-JsonAtomic -Object $manifest -Path $activeManifest

    Write-Host 'Re-verifying frozen Raven production state after rollback...'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw 'Transaction files were restored, but the frozen Raven production verifier did not pass. Do not launch God of War until the mismatch is reviewed.'
    }

    Write-Host ''
    Write-Host 'NORNIR_RUNTIME_TRANSACTION_ROLLED_BACK'
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host '  exact pre-install file state restored: true'
    Write-Host '  frozen Raven production verifier passed: true'
    Write-Host '  saves/progression/marker state touched by rollback: false'
    exit 0
}
