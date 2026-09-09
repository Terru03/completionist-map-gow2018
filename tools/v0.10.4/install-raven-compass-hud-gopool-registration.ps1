param(
    [ValidateSet('Install','Remove')]
    [string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/v104-raven-hud-research'
$ExpectedWadSha = '5d7cb3207275a6cd6d191d2878140d619716499464e4806af632c13172242e60'
$ExpectedBeforeDcbSha = 'b8d5627416787ae6761e0212a1e8de56e33abe7c251db838c4af20a00afc161b'
$ExpectedHudHash = '45E5C7943749F81C'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$StateDir = Join-Path $RepoRoot 'build\v0.10.4-raven-compass-hud-gopool-registration'
$CandidateDir = Join-Path $StateDir 'candidate'
$OfflineReport = Join-Path $StateDir 'offline-report.json'
$ManifestPath = Join-Path $StateDir 'active-install.json'
$BackupPath = Join-Path $StateDir 'wad_r_ui.dcb.before'
$LastRemovedPath = Join-Path $StateDir 'last-removed.json'
$Builder = Join-Path $PSScriptRoot 'build-raven-compass-hud-gopool-registration.py'

$WadTarget = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
$DcbTarget = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_ui.dcb'

function Get-Sha256([string]$Path) {
    return ((Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash).ToLowerInvariant()
}

function Assert-GameClosed {
    $running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessName -eq 'GoW' -or $_.ProcessName -eq 'GodOfWar'
    })
    if ($running.Count -gt 0) {
        throw 'God of War is running. Close the game before changing wad_r_ui.dcb.'
    }
}

function Assert-Branch {
    $branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
    if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) {
        throw "Expected Git branch '$ExpectedBranch', found '$branch'."
    }
}

function Write-JsonFile([object]$Object, [string]$Path) {
    $json = $Object | ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText($Path, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
}

Assert-GameClosed
Assert-Branch

if (-not (Test-Path -LiteralPath $WadTarget -PathType Leaf)) { throw "Missing $WadTarget" }
if (-not (Test-Path -LiteralPath $DcbTarget -PathType Leaf)) { throw "Missing $DcbTarget" }

$wadSha = Get-Sha256 $WadTarget
if ($wadSha -ne $ExpectedWadSha) {
    throw "r_ui.wad does not match the successful custom-WAD stock-art control. Expected $ExpectedWadSha, got $wadSha"
}

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        throw "No active HUD GOPool registration manifest exists at $ManifestPath"
    }
    if (-not (Test-Path -LiteralPath $BackupPath -PathType Leaf)) {
        throw "Active manifest exists but exact-byte DCB backup is missing: $BackupPath"
    }

    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    if ($manifest.schema -ne 1 -or $manifest.operation -ne 'raven_compass_hud_gopool_registration') {
        throw 'Active manifest is not a recognized Raven HUD GOPool registration manifest.'
    }
    if ($manifest.expected_wad_sha -ne $ExpectedWadSha) {
        throw 'Manifest WAD control hash does not match this installer.'
    }

    $liveSha = Get-Sha256 $DcbTarget
    if ($liveSha -ne $manifest.after_dcb_sha) {
        throw "Live wad_r_ui.dcb no longer matches the installed candidate. Expected $($manifest.after_dcb_sha), got $liveSha. Refusing to overwrite unknown state."
    }
    $backupSha = Get-Sha256 $BackupPath
    if ($backupSha -ne $manifest.before_dcb_sha -or $backupSha -ne $ExpectedBeforeDcbSha) {
        throw "Backup hash mismatch. Expected $ExpectedBeforeDcbSha, got $backupSha"
    }

    Copy-Item -LiteralPath $BackupPath -Destination $DcbTarget -Force
    $restoredSha = Get-Sha256 $DcbTarget
    if ($restoredSha -ne $ExpectedBeforeDcbSha) {
        throw "Rollback copy completed but restored DCB hash is wrong: $restoredSha"
    }

    $removed = [ordered]@{
        schema = 1
        operation = 'raven_compass_hud_gopool_registration'
        status = 'removed'
        removed_utc = [DateTime]::UtcNow.ToString('o')
        restored_dcb_sha = $restoredSha
        expected_wad_sha = $ExpectedWadSha
        game_files_touched = @('exec/dc/pc_le/wad_r_ui.dcb')
        saves_progression_marker_state_touched = $false
    }
    Write-JsonFile $removed $LastRemovedPath
    Remove-Item -LiteralPath $ManifestPath -Force

    Write-Host 'RAVEN_COMPASS_HUD_GOPOOL_REGISTRATION_REMOVED'
    Write-Host '  wad_r_ui.dcb restored byte-for-byte: true'
    Write-Host "  restored SHA256: $restoredSha"
    Write-Host '  r_ui.wad touched: false'
    Write-Host '  wad_r_perm/mapmaster/mapcoords/compassgraph touched: false'
    Write-Host '  saves/progression/marker state touched: false'
    exit 0
}

if (Test-Path -LiteralPath $ManifestPath -PathType Leaf) {
    throw "An active HUD GOPool registration manifest already exists: $ManifestPath. Remove it with -Mode Remove before installing again."
}

$beforeSha = Get-Sha256 $DcbTarget
if ($beforeSha -ne $ExpectedBeforeDcbSha) {
    throw "wad_r_ui.dcb is not the audited unregistered control. Expected $ExpectedBeforeDcbSha, got $beforeSha"
}
if (-not (Test-Path -LiteralPath $Builder -PathType Leaf)) {
    throw "Missing builder: $Builder"
}

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) {
    throw 'python.exe was not found on PATH.'
}

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
New-Item -ItemType Directory -Force -Path $CandidateDir | Out-Null

& $python.Source $Builder --game-root $GameRoot --work-dir $CandidateDir --output $OfflineReport
if ($LASTEXITCODE -ne 0) {
    throw "Offline GOPool registration builder failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $OfflineReport -PathType Leaf)) {
    throw 'Offline builder did not produce its report.'
}

$report = Get-Content -LiteralPath $OfflineReport -Raw | ConvertFrom-Json
if ($report.result -ne 'OFFLINE_RAVEN_COMPASS_HUD_GOPOOL_REGISTRATION_BUILT') {
    throw "Unexpected offline report result: $($report.result)"
}
if ($report.game_files_written -ne $false -or $report.save_progression_marker_state_written -ne $false) {
    throw 'Offline report does not prove the no-write safety contract.'
}
if ($report.source.'r_ui.wad'.sha256 -ne $ExpectedWadSha -or $report.source.'wad_r_ui.dcb'.sha256 -ne $ExpectedBeforeDcbSha) {
    throw 'Offline report source hashes do not match the pinned live control.'
}
if ($report.validation.hud_hash -ne $ExpectedHudHash -or $report.validation.hud_capacity -ne 1 -or $report.validation.hud_index -ne 256) {
    throw 'Offline report does not contain the exact expected HUD GOPool row contract.'
}
if ($report.validation.all_existing_gopool_rows_byte_identical -ne $true -or
    $report.validation.memorypools_lua_tail_byte_identical_after_shift -ne $true -or
    $report.validation.non_data_chunks_byte_identical -ne $true -or
    $report.validation.map_raven_row_preserved -ne $true -or
    $report.validation.stock_dock_row_preserved -ne $true) {
    throw 'Offline report preservation gates are not all green.'
}

$candidatePath = [string]$report.candidate.path
$candidateSha = [string]$report.candidate.sha256
if (-not (Test-Path -LiteralPath $candidatePath -PathType Leaf)) {
    throw "Candidate DCB is missing: $candidatePath"
}
if ((Get-Sha256 $candidatePath) -ne $candidateSha) {
    throw 'Candidate DCB hash differs from the offline report.'
}

Copy-Item -LiteralPath $DcbTarget -Destination $BackupPath -Force
if ((Get-Sha256 $BackupPath) -ne $ExpectedBeforeDcbSha) {
    throw 'Exact-byte backup verification failed. Live DCB has not been changed.'
}

$manifest = [ordered]@{
    schema = 1
    operation = 'raven_compass_hud_gopool_registration'
    status = 'prepared'
    prepared_utc = [DateTime]::UtcNow.ToString('o')
    branch = $ExpectedBranch
    expected_wad_sha = $ExpectedWadSha
    before_dcb_sha = $ExpectedBeforeDcbSha
    after_dcb_sha = $candidateSha
    hud_hash = $ExpectedHudHash
    hud_capacity = 1
    hud_index = 256
    backup_path = $BackupPath
    candidate_path = $candidatePath
    offline_report = $OfflineReport
    game_files_touched = @('exec/dc/pc_le/wad_r_ui.dcb')
    r_ui_wad_touched = $false
    wad_r_perm_mapmaster_mapcoords_compassgraph_touched = $false
    saves_progression_marker_state_touched = $false
}
Write-JsonFile $manifest $ManifestPath

try {
    Copy-Item -LiteralPath $candidatePath -Destination $DcbTarget -Force
    $afterSha = Get-Sha256 $DcbTarget
    if ($afterSha -ne $candidateSha) {
        throw "Installed candidate hash mismatch. Expected $candidateSha, got $afterSha"
    }

    $manifest['status'] = 'installed'
    $manifest['installed_utc'] = [DateTime]::UtcNow.ToString('o')
    Write-JsonFile $manifest $ManifestPath
}
catch {
    $installError = $_
    if (Test-Path -LiteralPath $BackupPath -PathType Leaf) {
        Copy-Item -LiteralPath $BackupPath -Destination $DcbTarget -Force
        $rollbackSha = Get-Sha256 $DcbTarget
        if ($rollbackSha -ne $ExpectedBeforeDcbSha) {
            throw "Install failed and automatic rollback also failed hash verification. Original error: $installError ; rollback SHA: $rollbackSha"
        }
    }
    if (Test-Path -LiteralPath $ManifestPath) {
        Remove-Item -LiteralPath $ManifestPath -Force
    }
    throw $installError
}

Write-Host 'RAVEN_COMPASS_HUD_GOPOOL_REGISTRATION_INSTALLED'
Write-Host "  wad_r_ui.dcb: $ExpectedBeforeDcbSha -> $candidateSha"
Write-Host '  GOPool rows: 256 -> 257'
Write-Host "  goCompletionistRavenHUD: $ExpectedHudHash, capacity 1, index 256"
Write-Host '  existing GOPool rows preserved byte-for-byte: true'
Write-Host '  MemoryPools/Lua tail preserved byte-for-byte after shift: true'
Write-Host '  r_ui.wad touched: false'
Write-Host '  wad_r_perm/mapmaster/mapcoords/compassgraph touched: false'
Write-Host '  saves/progression/marker state touched: false'
Write-Host '  DO NOT LAUNCH THE GAME YET.'
Write-Host '  Next gate: rerun run-raven-compass-hud-live-resolution-audit.ps1 and confirm the HUD pool is REGISTERED.'
