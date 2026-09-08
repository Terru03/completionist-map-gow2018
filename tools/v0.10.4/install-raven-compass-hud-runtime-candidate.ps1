param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [switch]$Rollback,
    [string]$ManifestPath = ''
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War completely before installing or rolling back the Raven compass HUD candidate.'
}

$game = (Resolve-Path -LiteralPath $GameRoot).Path
$liveWad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$liveDcb = Join-Path $game 'exec\dc\pc_le\wad_r_perm.dcb'
$buildRoot = Join-Path $repo 'build\v0.10.4\raven-compass-hud-four-payload'
$candidateWad = Join-Path $buildRoot 'r_ui.wad'
$candidateDcb = Join-Path $buildRoot 'wad_r_perm.dcb'
$combinedReportPath = Join-Path $repo 'archive\field-logs\completionist-v104-raven-compass-hud-combined-offline.json'
$backupRoot = Join-Path $buildRoot 'runtime-install-backups'

function Get-Sha256Lower([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing file: $Path"
    }
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Assert-Under([string]$Path, [string]$Tree, [string]$Label) {
    $full = [IO.Path]::GetFullPath($Path)
    $root = [IO.Path]::GetFullPath($Tree).TrimEnd('\') + '\'
    if (-not $full.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label must stay below $Tree, got $full"
    }
}

function Write-Manifest([string]$Path, [object]$Manifest) {
    $Manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Path -Encoding UTF8
}

if ($Rollback) {
    if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
        throw 'Rollback requires -ManifestPath <path printed by the installer>.'
    }
    $manifestFull = [IO.Path]::GetFullPath($ManifestPath)
    Assert-Under $manifestFull $backupRoot 'Rollback manifest'
    if (-not (Test-Path -LiteralPath $manifestFull -PathType Leaf)) {
        throw "Rollback manifest not found: $manifestFull"
    }
    $manifest = Get-Content -LiteralPath $manifestFull -Raw | ConvertFrom-Json
    if ([string]$manifest.kind -ne 'completionist-v104-raven-compass-hud-two-file-install') {
        throw 'Wrong rollback manifest kind.'
    }

    $backupWad = [string]$manifest.backups.r_ui_wad.path
    $backupDcb = [string]$manifest.backups.wad_r_perm_dcb.path
    Assert-Under $backupWad $backupRoot 'WAD backup'
    Assert-Under $backupDcb $backupRoot 'DCB backup'
    if ((Get-Sha256Lower $backupWad) -ne ([string]$manifest.backups.r_ui_wad.sha256).ToLowerInvariant()) {
        throw 'WAD backup hash mismatch.'
    }
    if ((Get-Sha256Lower $backupDcb) -ne ([string]$manifest.backups.wad_r_perm_dcb.sha256).ToLowerInvariant()) {
        throw 'DCB backup hash mismatch.'
    }

    Copy-Item -LiteralPath $backupWad -Destination $liveWad -Force
    Copy-Item -LiteralPath $backupDcb -Destination $liveDcb -Force

    $wadRestored = Get-Sha256Lower $liveWad
    $dcbRestored = Get-Sha256Lower $liveDcb
    if ($wadRestored -ne ([string]$manifest.live_sources.r_ui_wad_sha256).ToLowerInvariant()) {
        throw 'Rollback restored an unexpected r_ui.wad hash.'
    }
    if ($dcbRestored -ne ([string]$manifest.live_sources.wad_r_perm_dcb_sha256).ToLowerInvariant()) {
        throw 'Rollback restored an unexpected wad_r_perm.dcb hash.'
    }

    $manifest.state = 'rolled_back'
    $manifest.rolled_back_utc = [DateTime]::UtcNow.ToString('o')
    Write-Manifest $manifestFull $manifest

    Write-Host 'Raven compass HUD runtime candidate rolled back successfully.'
    Write-Host ("- restored r_ui.wad:      {0}" -f $wadRestored)
    Write-Host ("- restored wad_r_perm.dcb: {0}" -f $dcbRestored)
    Write-Host '- saves/progression/marker state touched: false'
    Write-Host ("- manifest: {0}" -f $manifestFull)
    exit 0
}

if (-not (Test-Path -LiteralPath $combinedReportPath -PathType Leaf)) {
    throw 'Combined offline report is missing. Run build-raven-compass-hud-offline-ready.ps1 first.'
}
$report = Get-Content -LiteralPath $combinedReportPath -Raw | ConvertFrom-Json
if ([string]$report.result -ne 'OFFLINE_RAVEN_COMPASS_HUD_COMBINED_CONTRACT_PASSED' -or
    [string]$report.conclusion -ne 'RAVEN_COMPASS_HUD_RUNTIME_CANDIDATE_READY' -or
    $report.ready_for_reversible_runtime_install -ne $true -or
    $report.safety.game_files_written -ne $false) {
    throw 'Combined offline report does not authorize a reversible install.'
}

foreach ($path in @($candidateWad, $candidateDcb, $liveWad, $liveDcb)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Required file missing: $path"
    }
}

Assert-Under $candidateWad $buildRoot 'WAD candidate'
Assert-Under $candidateDcb $buildRoot 'DCB candidate'

$expectedCandidateWad = ([string]$report.wad_candidate.sha256).ToLowerInvariant()
$expectedCandidateDcb = ([string]$report.dcb_candidate.sha256).ToLowerInvariant()
$expectedLiveWad = ([string]$report.live_sources.r_ui_wad_sha256).ToLowerInvariant()
$expectedLiveDcb = ([string]$report.live_sources.wad_r_perm_dcb_sha256).ToLowerInvariant()

if ((Get-Sha256Lower $candidateWad) -ne $expectedCandidateWad) {
    throw 'WAD candidate hash differs from combined offline report.'
}
if ((Get-Sha256Lower $candidateDcb) -ne $expectedCandidateDcb) {
    throw 'DCB candidate hash differs from combined offline report.'
}
if ((Get-Sha256Lower $liveWad) -ne $expectedLiveWad) {
    throw 'Live r_ui.wad changed since offline validation. Re-run the offline gate.'
}
if ((Get-Sha256Lower $liveDcb) -ne $expectedLiveDcb) {
    throw 'Live wad_r_perm.dcb changed since offline validation. Re-run the offline gate.'
}

$stamp = [DateTime]::UtcNow.ToString('yyyyMMdd-HHmmss')
$backupDir = Join-Path $backupRoot $stamp
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$backupWad = Join-Path $backupDir 'r_ui.wad.before-raven-hud'
$backupDcb = Join-Path $backupDir 'wad_r_perm.dcb.before-raven-hud'
$manifestFull = Join-Path $backupDir 'install-manifest.json'

Copy-Item -LiteralPath $liveWad -Destination $backupWad
Copy-Item -LiteralPath $liveDcb -Destination $backupDcb
if ((Get-Sha256Lower $backupWad) -ne $expectedLiveWad) { throw 'WAD backup verification failed.' }
if ((Get-Sha256Lower $backupDcb) -ne $expectedLiveDcb) { throw 'DCB backup verification failed.' }

$manifest = [ordered]@{
    kind = 'completionist-v104-raven-compass-hud-two-file-install'
    state = 'backup_complete'
    created_utc = [DateTime]::UtcNow.ToString('o')
    branch = $branch
    game_root = $game
    live_sources = [ordered]@{
        r_ui_wad_sha256 = $expectedLiveWad
        wad_r_perm_dcb_sha256 = $expectedLiveDcb
    }
    candidates = [ordered]@{
        r_ui_wad = [ordered]@{ path = $candidateWad; sha256 = $expectedCandidateWad }
        wad_r_perm_dcb = [ordered]@{ path = $candidateDcb; sha256 = $expectedCandidateDcb }
    }
    backups = [ordered]@{
        r_ui_wad = [ordered]@{ path = $backupWad; sha256 = $expectedLiveWad }
        wad_r_perm_dcb = [ordered]@{ path = $backupDcb; sha256 = $expectedLiveDcb }
    }
    combined_report = $combinedReportPath
    save_progression_marker_state_written = $false
}
Write-Manifest $manifestFull $manifest

try {
    Copy-Item -LiteralPath $candidateWad -Destination $liveWad -Force
    Copy-Item -LiteralPath $candidateDcb -Destination $liveDcb -Force

    $installedWad = Get-Sha256Lower $liveWad
    $installedDcb = Get-Sha256Lower $liveDcb
    if ($installedWad -ne $expectedCandidateWad) { throw 'Installed r_ui.wad hash mismatch.' }
    if ($installedDcb -ne $expectedCandidateDcb) { throw 'Installed wad_r_perm.dcb hash mismatch.' }

    $manifest.state = 'installed'
    $manifest.installed_utc = [DateTime]::UtcNow.ToString('o')
    Write-Manifest $manifestFull $manifest
}
catch {
    $installError = $_
    try {
        Copy-Item -LiteralPath $backupWad -Destination $liveWad -Force
        Copy-Item -LiteralPath $backupDcb -Destination $liveDcb -Force
        if ((Get-Sha256Lower $liveWad) -ne $expectedLiveWad -or
            (Get-Sha256Lower $liveDcb) -ne $expectedLiveDcb) {
            throw 'Automatic rollback verification failed.'
        }
        $manifest.state = 'auto_rolled_back_after_install_failure'
        $manifest.rollback_utc = [DateTime]::UtcNow.ToString('o')
        $manifest.install_error = [string]$installError.Exception.Message
        Write-Manifest $manifestFull $manifest
    }
    catch {
        throw "Install failed and automatic rollback also failed. Original install error: $($installError.Exception.Message). Rollback error: $($_.Exception.Message). Backups: $backupDir"
    }
    throw "Install failed; both game files were automatically restored. Error: $($installError.Exception.Message)"
}

Write-Host 'Raven compass HUD runtime candidate installed as a validated two-file pair.'
Write-Host ("- r_ui.wad SHA256:      {0}" -f $expectedCandidateWad)
Write-Host ("- wad_r_perm.dcb SHA256: {0}" -f $expectedCandidateDcb)
Write-Host '- working map Raven source preserved by offline invariance gate'
Write-Host '- stock DockPoint source preserved by offline invariance gate'
Write-Host '- saves/progression/marker state touched: false'
Write-Host '- God of War was not launched'
Write-Host ("- rollback manifest: {0}" -f $manifestFull)
Write-Host ''
Write-Host 'Rollback command:'
Write-Host ("powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Rollback -ManifestPath `"{1}`"" -f $PSCommandPath, $manifestFull)
