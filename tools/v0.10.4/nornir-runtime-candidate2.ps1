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
$stateRoot = Join-Path $repo 'build\v0.10.4-nornir-runtime-candidate2\transaction'
$activeManifest = Join-Path $stateRoot 'active.json'
$candidateRoot = Join-Path $repo 'build\v0.10.4-nornir-runtime-candidate2\offline\candidate\game-root'
$localReport = Join-Path $repo 'build\v0.10.4-nornir-runtime-candidate2\offline\nornir-runtime-candidate2.json'
$archivedReport = Join-Path $repo 'archive\field-logs\completionist-v104-nornir-runtime-candidate2-offline.json'
$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'

$files = [ordered]@{
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

function Get-Sha256([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing file: $Path" }
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-GameClosed {
    if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War first.' }
    if (Get-Process -Name GodOfWar -ErrorAction SilentlyContinue) { throw 'Close God of War first.' }
}

function Assert-Branch {
    $branch = (& git -C $repo branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not determine Git branch.' }
    if ($branch -ne $expectedBranch) { throw "Expected branch '$expectedBranch', got '$branch'." }
    $branch
}

function Write-JsonAtomic([object]$Value, [string]$Path) {
    $parent = Split-Path $Path -Parent
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $temp = "$Path.tmp-$([Guid]::NewGuid().ToString('N'))"
    $encoding = New-Object System.Text.UTF8Encoding($false)
    try {
        $json = $Value | ConvertTo-Json -Depth 20
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
        if ((Get-Sha256 $temp) -ne $ExpectedSha) { throw "Temporary SHA mismatch: $Destination" }
        Move-Item -LiteralPath $temp -Destination $Destination -Force
        if ((Get-Sha256 $Destination) -ne $ExpectedSha) { throw "Installed SHA mismatch: $Destination" }
    }
    finally {
        Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
    }
}

function Assert-ProofObject([object]$Proof) {
    if ($Proof.result -ne 'OFFLINE_NORNIR_RUNTIME_CANDIDATE2_ASSEMBLED') { throw 'Unexpected Candidate 2 proof result.' }
    if (-not $Proof.proofs.exactly_ten_files_present) { throw 'Candidate 2 proof does not contain exactly ten files.' }
    if (-not $Proof.proofs.only_r_ui_wad_differs_from_lifecycle_candidate) { throw 'Candidate 2 proof changes more than r_ui.wad.' }
    if (-not $Proof.proofs.r_ui_wad_is_exact_isolated_mg_candidate) { throw 'Candidate 2 r_ui.wad is not the isolated MG candidate.' }
    if (-not $Proof.proofs.all_other_nine_files_byte_identical_to_lifecycle_candidate) { throw 'Candidate 2 non-WAD files differ from lifecycle candidate.' }
    if (-not $Proof.proofs.isolated_mg_audit_cleared_runtime_candidate_2_assembly) { throw 'Candidate 2 isolation audit gate is not passed.' }
    if (-not $Proof.proofs.candidate2_ready_for_transactional_installer_gate) { throw 'Candidate 2 is not cleared for transactional install.' }
    if ($Proof.safety.game_files_written -or $Proof.safety.runtime_install_performed -or $Proof.safety.save_state_written -or $Proof.safety.progression_state_written -or $Proof.safety.marker_state_written) {
        throw 'Candidate 2 offline safety contract is not clean.'
    }
}

function Assert-Candidate2 {
    foreach ($required in @($candidateRoot, $localReport, $archivedReport, $verifyRaven)) {
        if (-not (Test-Path -LiteralPath $required)) {
            throw "Missing Candidate 2 prerequisite: $required`nRe-run .\tools\v0.10.4\run-nornir-runtime-candidate2-offline.ps1 first."
        }
    }

    $local = Get-Content -LiteralPath $localReport -Raw | ConvertFrom-Json
    $archive = Get-Content -LiteralPath $archivedReport -Raw | ConvertFrom-Json
    Assert-ProofObject $local
    Assert-ProofObject $archive

    foreach ($name in $files.Keys) {
        $localProperty = $local.files.PSObject.Properties[$name]
        $archiveProperty = $archive.files.PSObject.Properties[$name]
        if ($null -eq $localProperty -or $null -eq $archiveProperty) { throw "Missing proof entry: $name" }

        $localSha = ([string]$localProperty.Value.candidate2_sha256).ToLowerInvariant()
        $archiveSha = ([string]$archiveProperty.Value.candidate2_sha256).ToLowerInvariant()
        if ($localSha -ne $archiveSha) { throw "Local/archive Candidate 2 SHA mismatch: $name" }

        $source = Join-Path $candidateRoot $files[$name]
        if ((Get-Sha256 $source) -ne $archiveSha) { throw "Candidate 2 file SHA mismatch: $name" }

        if ($name -eq 'r_ui.wad') {
            $lifecycleSha = ([string]$archiveProperty.Value.lifecycle_sha256).ToLowerInvariant()
            if ($archiveSha -eq $lifecycleSha) { throw 'Candidate 2 r_ui.wad unexpectedly equals lifecycle r_ui.wad.' }
        }
        else {
            $lifecycleSha = ([string]$archiveProperty.Value.lifecycle_sha256).ToLowerInvariant()
            if ($archiveSha -ne $lifecycleSha) { throw "Unexpected non-r_ui.wad Candidate 2 change: $name" }
        }
    }

    $archive
}

function Restore-State([object]$Manifest, [bool]$CheckInstalled, [bool]$Force) {
    Assert-GameClosed

    if ($CheckInstalled -and -not $Force) {
        foreach ($entry in @($Manifest.entries)) {
            $dest = Join-Path $GameRoot ([string]$entry.relative)
            if (-not (Test-Path -LiteralPath $dest -PathType Leaf)) { throw "Installed file missing before rollback: $($entry.name)" }
            if ((Get-Sha256 $dest) -ne ([string]$entry.candidate_sha256).ToLowerInvariant()) {
                throw "Installed file changed since Candidate 2 install: $($entry.name). Use -ForceRollback only after reviewing it."
            }
        }
    }

    $reverse = @($Manifest.entries)
    [array]::Reverse($reverse)
    foreach ($entry in $reverse) {
        $dest = Join-Path $GameRoot ([string]$entry.relative)
        if ([bool]$entry.existed_before) {
            $backup = Join-Path ([string]$Manifest.transaction_root) ([string]$entry.backup_relative)
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
        $dest = Join-Path $GameRoot ([string]$entry.relative)
        if ([bool]$entry.existed_before) {
            if ((Get-Sha256 $dest) -ne ([string]$entry.before_sha256).ToLowerInvariant()) { throw "Rollback verification failed: $($entry.name)" }
        }
        elseif (Test-Path -LiteralPath $dest) {
            throw "Rollback expected file to be absent: $($entry.name)"
        }
    }
}

if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

if ($Mode -eq 'Status') {
    Write-Host 'NORNIR_RUNTIME_CANDIDATE2_STATUS'
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

$branch = Assert-Branch
Assert-GameClosed

if ($Mode -eq 'Install') {
    if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
        $old = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
        if ($old.status -in @('backup-complete','installing','installed')) {
            throw "Active Candidate 2 transaction already exists with status '$($old.status)'. Roll it back first."
        }
    }

    $proof = Assert-Candidate2

    Write-Host 'Re-verifying frozen Raven production immediately before Candidate 2 install...'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verification failed. Candidate 2 was not installed.' }

    $transactionId = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
    $transactionRoot = Join-Path $stateRoot ('transactions\' + $transactionId)
    $backupRoot = Join-Path $transactionRoot 'backup\game-root'
    $transactionManifest = Join-Path $transactionRoot 'manifest.json'
    New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

    $entries = @()
    foreach ($name in $files.Keys) {
        $relative = $files[$name]
        $source = Join-Path $candidateRoot $relative
        $dest = Join-Path $GameRoot $relative
        $proofEntry = $proof.files.PSObject.Properties[$name].Value
        $candidateSha = ([string]$proofEntry.candidate2_sha256).ToLowerInvariant()
        if ((Get-Sha256 $source) -ne $candidateSha) { throw "Candidate changed after proof validation: $name" }

        $existed = Test-Path -LiteralPath $dest -PathType Leaf
        $beforeSha = $null
        $backupRelative = $null
        if ($existed) {
            $beforeSha = Get-Sha256 $dest
            $backupRelative = 'backup\game-root\' + $relative
            $backup = Join-Path $transactionRoot $backupRelative
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
        candidate = 'nornir-runtime-candidate2'
        transaction_id = $transactionId
        status = 'backup-complete'
        created_utc = (Get-Date).ToUniversalTime().ToString('o')
        installed_utc = $null
        rolled_back_utc = $null
        game_root = $GameRoot
        repo_branch = $branch
        repo_head = (& git -C $repo rev-parse HEAD).Trim()
        transaction_root = $transactionRoot
        archived_proof = $archivedReport
        entries = $entries
        safety = [ordered]@{
            backup_complete_before_first_game_write = $true
            automatic_rollback_on_install_failure = $true
            save_files_written_by_installer = $false
            progression_state_written_by_installer = $false
            marker_state_written_by_installer = $false
        }
    }

    Write-JsonAtomic $manifest $transactionManifest
    Write-JsonAtomic $manifest $activeManifest

    try {
        $manifest.status = 'installing'
        Write-JsonAtomic $manifest $transactionManifest
        Write-JsonAtomic $manifest $activeManifest

        foreach ($entry in $entries) {
            $source = Join-Path $candidateRoot ([string]$entry.relative)
            $dest = Join-Path $GameRoot ([string]$entry.relative)
            Copy-Verified -Source $source -Destination $dest -ExpectedSha ([string]$entry.candidate_sha256)
            Write-Host "  installed $($entry.name)"
        }

        foreach ($entry in $entries) {
            $dest = Join-Path $GameRoot ([string]$entry.relative)
            if ((Get-Sha256 $dest) -ne ([string]$entry.candidate_sha256).ToLowerInvariant()) { throw "Post-install verification failed: $($entry.name)" }
        }

        $manifest.status = 'installed'
        $manifest.installed_utc = (Get-Date).ToUniversalTime().ToString('o')
        Write-JsonAtomic $manifest $transactionManifest
        Write-JsonAtomic $manifest $activeManifest
    }
    catch {
        $installError = $_.Exception.Message
        Write-Warning "Candidate 2 install failed: $installError"
        Write-Warning 'Restoring the complete pre-install state...'
        try {
            Restore-State -Manifest $manifest -CheckInstalled $false -Force $true
            $manifest.status = 'rolled-back-after-install-failure'
            $manifest.rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
            Write-JsonAtomic $manifest $transactionManifest
            Write-JsonAtomic $manifest $activeManifest
            throw "Candidate 2 install failed and was automatically rolled back. Original error: $installError"
        }
        catch {
            if ($manifest.status -ne 'rolled-back-after-install-failure') {
                $rollbackError = $_.Exception.Message
                $manifest.status = 'rollback-failed-after-install-failure'
                Write-JsonAtomic $manifest $transactionManifest
                Write-JsonAtomic $manifest $activeManifest
                throw "Candidate 2 install failed: $installError`nAutomatic rollback also failed: $rollbackError`nDo not launch God of War until reviewed."
            }
            throw
        }
    }

    Write-Host ''
    Write-Host 'NORNIR_RUNTIME_CANDIDATE2_INSTALLED'
    Write-Host "  transaction: $transactionId"
    Write-Host '  Candidate 2 proof verified: true'
    Write-Host '  ten files installed and SHA-verified: true'
    Write-Host '  all pre-install backups completed before first game write: true'
    Write-Host '  saves/progression/marker state written by installer: false'
    Write-Host "  manifest: $transactionManifest"
    exit 0
}

if ($Mode -eq 'Rollback') {
    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) { throw 'No Candidate 2 transaction exists.' }
    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    if ($manifest.status -ne 'installed' -and -not $ForceRollback) {
        throw "Candidate 2 transaction status is '$($manifest.status)', not 'installed'."
    }
    if ([string]$manifest.game_root -ne $GameRoot) { throw "Transaction belongs to a different game root: $($manifest.game_root)" }

    Restore-State -Manifest $manifest -CheckInstalled $true -Force ([bool]$ForceRollback)

    $manifest.status = 'rolled-back'
    $manifest.rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
    $transactionManifest = Join-Path ([string]$manifest.transaction_root) 'manifest.json'
    Write-JsonAtomic $manifest $transactionManifest
    Write-JsonAtomic $manifest $activeManifest

    Write-Host 'Re-verifying frozen Raven production after Candidate 2 rollback...'
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Rollback restored files, but Raven production verification failed. Do not launch God of War until reviewed.' }

    Write-Host ''
    Write-Host 'NORNIR_RUNTIME_CANDIDATE2_ROLLED_BACK'
    Write-Host "  transaction: $($manifest.transaction_id)"
    Write-Host '  exact pre-install state restored: true'
    Write-Host '  Raven production verifier passed: true'
    Write-Host '  saves/progression/marker state touched by rollback: false'
    exit 0
}
