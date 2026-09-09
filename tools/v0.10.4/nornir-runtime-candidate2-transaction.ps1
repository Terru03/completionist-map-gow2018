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
$runtimeState = Join-Path $repo 'build\v0.10.4-nornir-runtime-candidate2\transaction'
$activeManifest = Join-Path $runtimeState 'active.json'
$candidateRoot = Join-Path $repo 'build\v0.10.4-nornir-runtime-candidate2\offline\candidate\game-root'
$localReport = Join-Path $repo 'build\v0.10.4-nornir-runtime-candidate2\offline\nornir-runtime-candidate2.json'
$archivedReport = Join-Path $repo 'archive\field-logs\completionist-v104-nornir-runtime-candidate2-offline.json'
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
    if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before changing the Candidate 2 runtime transaction.' }
    if (Get-Process -Name GodOfWar -ErrorAction SilentlyContinue) { throw 'Close God of War before changing the Candidate 2 runtime transaction.' }
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

function Copy-VerifiedFile([string]$Source, [string]$Destination, [string]$ExpectedSha) {
    $parent = Split-Path $Destination -Parent
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $tmp = $Destination + '.completionist-candidate2-tmp-' + [Guid]::NewGuid().ToString('N')
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

function Assert-Candidate2 {
    foreach ($required in @($candidateRoot, $localReport, $archivedReport, $verifyRaven)) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Missing Candidate 2 prerequisite: $required`nRe-run tools\v0.10.4\run-nornir-runtime-candidate2-offline.ps1 first."
        }
    }

    $local = Get-Content -LiteralPath $localReport -Raw | ConvertFrom-Json
    $archived = Get-Content -LiteralPath $archivedReport -Raw | ConvertFrom-Json

    foreach ($proof in @($local, $archived)) {
        if ($proof.result -ne 'OFFLINE_NORNIR_RUNTIME_CANDIDATE2_ASSEMBLED' -or
            -not $proof.proofs.exactly_ten_files_present -or
            -not $proof.proofs.only_r_ui_wad_differs_from_lifecycle_candidate -or
            -not $proof.proofs.r_ui_wad_is_exact_isolated_mg_candidate -or
            -not $proof.proofs.all_other_nine_files_byte_identical_to_lifecycle_candidate -or
            -not $proof.proofs.isolated_mg_audit_cleared_runtime_candidate_2_assembly -or
            -not $proof.proofs.candidate2_ready_for_transactional_installer_gate -or
            $proof.safety.game_files_written -or
            $proof.safety.runtime_install_performed -or
            $proof.safety.save_state_written -or
            $proof.safety.progression_state_written -or
            $proof.safety.marker_state_written) {
            throw 'Candidate 2 proof is not an approved passing offline candidate.'
        }
    }

    foreach ($name in $expected.Keys) {
        $localProperty = $local.files.PSObject.Properties[$name]
        $archiveProperty = $archived.files.PSObject.Properties[$name]
        if ($null -eq $localProperty -or $null -eq $archiveProperty) { throw "Candidate 2 report entry missing: $name" }

        $localEntry = $localProperty.Value
        $archiveEntry = $archiveProperty.Value
        $localSha = ([string]$localEntry.candidate2_sha256).ToLowerInvariant()
        $archiveSha = ([string]$archiveEntry.candidate2_sha256).ToLowerInvariant()
        if ($localSha -ne $archiveSha) { throw "Local Candidate 2 report differs from archived proof: $name" }

        $source = Join-Path $candidateRoot $expected[$name]
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw "Candidate 2 file missing: $name" }
        if ((Get-Sha256 $source) -ne $archiveSha) { throw "Candidate 2 SHA mismatch against archived proof: $name" }
    }

    if (([string]$archived.files.'r_ui.wad'.candidate2_sha256).ToLowerInvariant() -eq
        ([string]$archived.files.'r_ui.wad'.lifecycle_sha256).ToLowerInvariant()) {
        throw 'Candidate 2 r_ui.wad unexpectedly matches the lifecycle candidate.'
    }

    foreach ($name in $expected.Keys | Where-Object { $_ -ne 'r_ui.wad' }) {
        $entry = $archived.files.PSObject.Properties[$name].Value
        if (([string]$entry.candidate2_sha256).ToLowerInvariant() -ne ([string]$entry.lifecycle_sha256).ToLowerInvariant()) {
            throw "Candidate 2 unexpectedly changes a non-r_ui.wad file: $name"
        }
    }

    return $archived
}

function Restore-Transaction([object]$Manifest, [string]$TransactionRoot, [bool]$RequireInstalledCandidate, [bool]$Force) {
    Assert-GodOfWarClosed

    if ($RequireInstalledCandidate -and -not $Force) {
        foreach ($entry in @($Manifest.entries)) {
            $dest = Join-Path $GameRoot ([string]$entry.relative)
            if (-not (Test-Path -LiteralPath $dest -PathType Leaf)) {
                throw "Rollback safety check: installed destination missing: $($entry.name). Use -ForceRollback only after reviewing the file state."
            }
            if ((Get-Sha256 $dest) -ne ([string]$entry.candidate_sha256).ToLowerInvariant()) {
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
        Write-Host 'NORNIR_RUNTIME_CANDIDATE2_TRANSACTION_STATUS'
        Write-Host '  active transaction: none'
        exit 0
    }

    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    Write-Host 'NORNIR_RUNTIME_CANDIDATE2_TRANSACTION_STATUS'
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
            throw "An active Candidate 2 transaction already exists with status '$($previous.status)'. Roll it back before installing again."
        }
    }

    $proof = Assert-Candidate2

    Write-Host 'Re-verifying frozen Raven production state immediately before Candidate 2 install...'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production state must pass before Candidate 2 is installed.' }

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
        $candidateSha = ([string]$proof.files.PSObject.Properties[$name].Value.candidate2_sha256).ToLowerInvariant()
        if ((Get-Sha256 $source) -ne $candidateSha) { throw "Candidate changed after Candidate 2 verification: $name" }

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
        candidate = 'nornir-runtime-candidate2'
        transaction_id = $transactionId
        status = 'backup-complete'
        created_utc = (Get-Date).ToUniversalTime().ToString('o')
        installed_utc = $null
        rolled_back_utc = $null
        game_root = $GameRoot
        repo_branch = $branch
        repo_head = (& git -C $repo rev-parse HEAD).Trim()
        source_archived_report = $archivedReport
        transaction_root = $transactionRoot
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
                throw "Post-install Candidate 2 SHA verification failed: $($entry.name)"
            }
        }

        $manifest.status = 'installed'
        $manifest.installed_utc = (Get-Date).ToUniversalTime().ToString('o')
        Write-JsonAtomic -Object $manifest -Path $transactionManifest
        Write-JsonAtomic -Object $manifest -Path $activeManifest
    }
    catch {
        $installError = $_.Exception.Message
        Write-Warning "Candidate 2 install failed: $installError"
        Write-Warning 'Attempting automatic restoration of the complete pre-install state...'
        try {
            Restore-Transaction -Manifest $manifest -TransactionRoot $transactionRoot -RequireInstalledCandidate $false -Force $true
            $manifest.status = 'rolled-back-after-install-failure'
            $manifest.rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
            Write-JsonAtomic -Object $manifest -Path $transactionManifest
            Write-JsonAtomic -Object $manifest -Path $activeManifest
            throw "Candidate 2 install failed and the complete pre-install file state was automatically restored. Original error: $installError"
        }
        catch {
            if ($manifest.status -ne 'rolled-back-after-install-failure') {
                $rollbackError = $_.Exception.Message
                $manifest.status = 'rollback-failed-after-install-failure'
                Write-JsonAtomic -Object $manifest -Path $transactionManifest
                Write-JsonAtomic -Object $manifest -Path $activeManifest
                throw "Candidate 2 install failed: $installError`nAutomatic rollback also failed: $rollbackError`nDo not launch God of War until the transaction is repaired."
            }
            throw
        }
    }

    Write-Host ''
    Write-Host 'NORNIR_RUNTIME_CANDIDATE2_TRANSACTION_INSTALLED'
    Write-Host "  transaction: $transactionId"
    Write-Host '  ten Candidate 2 files installed and SHA-verified: true'
    Write-Host '  complete pre-install backups created before first game write: true'
    Write-Host '  archived Candidate 2 proof matched local build: true'
    Write-Host '  Raven production baseline verified immediately before install: true'
    Write-Host '  saves/progression/marker state written by installer: false'
    Write-Host "  backup root: $backupRoot"
    Write-Host "  manifest: $transactionManifest"
    Write-Host ''
    Write-Host 'Rollback command (with God of War closed):'
    Write-Host '  powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\tools\v0.10.4\nornir-runtime-candidate2-transaction.ps1" -Mode Rollback'
    Write-Host ''
    Write-Host 'Use a disposable test save for the runtime test. Do not test collectible completion on your master/public save.'
    exit 0
}

if ($Mode -eq 'Rollback') {
    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) { throw 'No Candidate 2 runtime transaction manifest exists to roll back.' }
    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    if ($manifest.status -ne 'installed' -and -not $ForceRollback) {
        throw "Active Candidate 2 transaction status is '$($manifest.status)', not 'installed'. Use -ForceRollback only after reviewing the transaction state."
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

    Write-Host 'Re-verifying frozen Raven production state after Candidate 2 rollback...'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw 'Candidate 2 files were restored, but the frozen Raven production verifier did not pass. Do not launch God of War until the mismatch is reviewed.'
    }

    Write-Host ''
    Write-Host 'NORNIR_RUNTIME_CANDIDATE2_TRANSACTION_ROLLED_BACK'
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host '  exact pre-install file state restored: true'
    Write-Host '  frozen Raven production verifier passed: true'
    Write-Host '  saves/progression/marker state touched by rollback: false'
    exit 0
}
