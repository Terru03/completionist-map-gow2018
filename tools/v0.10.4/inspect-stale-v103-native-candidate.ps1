param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected branch codex/v104-raven-hud-research, got '$branch'."
}

$game = [IO.Path]::GetFullPath($GameRoot)
$mapTarget = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$ravenTarget = Join-Path $game 'mods\lua\gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
$candidateDir = Join-Path $repo 'build\v0.10.3-native-raven-candidate'
$candidateManifest = Join-Path $candidateDir 'active.json'
$mapBackup = Join-Path $candidateDir 'mapmenu-before.lua'
$ravenBackup = Join-Path $candidateDir 'precisionchallenge-before.lua'
$dcbDir = Join-Path $repo 'build\v0.10.3-native-raven-dcb'
$dcbManifest = Join-Path $dcbDir 'active.json'
$gameDcbDir = Join-Path $game 'exec\dc\pc_le'
$outRel = 'archive/field-logs/completionist-v104-stale-v103-native-candidate-state.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

function Hash-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Count-Literal([string]$Text, [string]$Needle) {
    if ([string]::IsNullOrEmpty($Text) -or [string]::IsNullOrEmpty($Needle)) { return 0 }
    $count = 0
    $at = 0
    while ($true) {
        $i = $Text.IndexOf($Needle, $at, [StringComparison]::Ordinal)
        if ($i -lt 0) { break }
        $count++
        $at = $i + $Needle.Length
    }
    return $count
}

function File-State([string]$Target, [string]$Backup, $Manifest, [string]$BeforeField, [string]$AfterField, [string[]]$Markers) {
    $currentText = if (Test-Path -LiteralPath $Target -PathType Leaf) { [IO.File]::ReadAllText($Target) } else { $null }
    $backupText = if (Test-Path -LiteralPath $Backup -PathType Leaf) { [IO.File]::ReadAllText($Backup) } else { $null }
    $currentHash = Hash-File $Target
    $backupHash = Hash-File $Backup
    $before = if ($null -ne $Manifest) { ([string]$Manifest.$BeforeField).ToUpperInvariant() } else { $null }
    $after = if ($null -ne $Manifest) { ([string]$Manifest.$AfterField).ToUpperInvariant() } else { $null }

    $markerState = [ordered]@{}
    foreach ($marker in $Markers) {
        $markerState[$marker] = if ($null -ne $currentText) { Count-Literal $currentText $marker } else { 0 }
    }

    [ordered]@{
        target = $Target
        exists = Test-Path -LiteralPath $Target -PathType Leaf
        current_sha256 = $currentHash
        backup = $Backup
        backup_exists = Test-Path -LiteralPath $Backup -PathType Leaf
        backup_sha256 = $backupHash
        manifest_before_sha256 = $before
        manifest_after_sha256 = $after
        current_equals_manifest_before = ($null -ne $currentHash -and $currentHash -eq $before)
        current_equals_manifest_after = ($null -ne $currentHash -and $currentHash -eq $after)
        backup_equals_manifest_before = ($null -ne $backupHash -and $backupHash -eq $before)
        current_starts_with_backup_bytes = ($null -ne $currentText -and $null -ne $backupText -and $currentText.StartsWith($backupText, [StringComparison]::Ordinal))
        current_length_chars = if ($null -ne $currentText) { $currentText.Length } else { 0 }
        backup_length_chars = if ($null -ne $backupText) { $backupText.Length } else { 0 }
        markers = $markerState
    }
}

$candidate = if (Test-Path -LiteralPath $candidateManifest -PathType Leaf) {
    Get-Content -LiteralPath $candidateManifest -Raw | ConvertFrom-Json
} else { $null }

$dcb = if (Test-Path -LiteralPath $dcbManifest -PathType Leaf) {
    Get-Content -LiteralPath $dcbManifest -Raw | ConvertFrom-Json
} else { $null }

$mapMarkers = @(
    'BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE',
    'END COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE',
    'BEGIN COMPLETIONIST V0.10.4 DEDICATED RAVEN COMPASS CLASS',
    'BEGIN COMPLETIONIST V0.10.4 RAVEN',
    'goMapIconCompletionistRaven',
    '[CompletionistMap v0.10.1] MAP_SCRIPT_LOADED'
)
$ravenMarkers = @(
    'BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN LIFECYCLE BRIDGE',
    'END COMPLETIONIST V0.10.3 NATIVE RAVEN LIFECYCLE BRIDGE',
    '[CompletionistMap v0.10.1] RAVEN_STATE',
    'CompletionistMapV100_IsTargetRaven'
)

$dcbRows = [ordered]@{}
foreach ($name in @('mapmaster.dcb','mapcoords.dcb','compassgraph.dcb')) {
    $target = Join-Path $gameDcbDir $name
    $current = Hash-File $target
    $stock = $null
    $patched = $null
    if ($null -ne $dcb) {
        $stock = ([string]$dcb.stock_hashes.$name).ToUpperInvariant()
        $patched = ([string]$dcb.patched_hashes.$name).ToUpperInvariant()
    }
    $dcbRows[$name] = [ordered]@{
        current_sha256 = $current
        manifest_stock_sha256 = $stock
        manifest_patched_sha256 = $patched
        current_is_stock = ($null -ne $current -and $current -eq $stock)
        current_is_patched = ($null -ne $current -and $current -eq $patched)
    }
}

$report = [ordered]@{
    result = 'READ_ONLY_STALE_V103_NATIVE_CANDIDATE_STATE'
    captured_utc = [DateTime]::UtcNow.ToString('o')
    game_process_running = [bool](Get-Process -Name GoW -ErrorAction SilentlyContinue)
    steam_process_running = [bool](Get-Process -Name steam -ErrorAction SilentlyContinue)
    game_files_written = $false
    candidate_manifest = [ordered]@{
        path = $candidateManifest
        active_exists = Test-Path -LiteralPath $candidateManifest -PathType Leaf
        candidate = if ($null -ne $candidate) { [string]$candidate.candidate } else { $null }
        candidate_hash = if ($null -ne $candidate) { [string]$candidate.candidate_hash } else { $null }
        installed_utc = if ($null -ne $candidate) { [string]$candidate.installed_utc } else { $null }
    }
    mapmenu = File-State $mapTarget $mapBackup $candidate 'map_before' 'map_after' $mapMarkers
    precisionchallenge = File-State $ravenTarget $ravenBackup $candidate 'raven_before' 'raven_after' $ravenMarkers
    native_raven_dcb_manifest = [ordered]@{
        path = $dcbManifest
        active_exists = Test-Path -LiteralPath $dcbManifest -PathType Leaf
        files = $dcbRows
    }
    interpretation = 'READ_ONLY_ONLY__DO_NOT_DELETE_ACTIVE_JSON_OR_OVERWRITE_FILES_FROM_THIS_REPORT_ALONE'
}

New-Item -ItemType Directory -Force -Path (Split-Path $out -Parent) | Out-Null
$utf8 = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($out, ($report | ConvertTo-Json -Depth 10) + "`n", $utf8)
Write-Host "Wrote read-only stale-candidate report: $out"
Write-Host "- GoW running: $($report.game_process_running)"
Write-Host "- Steam running: $($report.steam_process_running)"
Write-Host "- candidate active manifest: $($report.candidate_manifest.active_exists)"
Write-Host "- native Raven DCB active manifest: $($report.native_raven_dcb_manifest.active_exists)"
Write-Host '- game files written: false'

& git -C $repo add -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
& git -C $repo diff --cached --check -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
& git -C $repo diff --cached --quiet -- $outRel
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Report unchanged; nothing new to commit.'
    return
}
& git -C $repo commit -m 'Archive stale v0.10.3 native candidate state' -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
& git -C $repo push $Remote $branch
if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
Write-Host "Pushed report to $Remote/$branch"
