param(
    [ValidateSet('Apply')][string]$Mode = 'Apply',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected branch codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before cleaning the stale v0.10.3 candidate state.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$mapTarget = Join-Path $game 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
$ravenTarget = Join-Path $game 'mods\lua\gameart\scripts\levels\gameplaymodules\progression\precisionchallenge.lua'
$dcbDir = Join-Path $game 'exec\dc\pc_le'

$candidateState = Join-Path $repo 'build\v0.10.3-native-raven-candidate'
$candidateManifestPath = Join-Path $candidateState 'active.json'
$mapBackup = Join-Path $candidateState 'mapmenu-before.lua'
$ravenBackup = Join-Path $candidateState 'precisionchallenge-before.lua'

$dcbState = Join-Path $repo 'build\v0.10.3-native-raven-dcb'
$dcbManifestPath = Join-Path $dcbState 'active.json'
$dcbBackupDir = Join-Path $dcbState 'stock-backup'

$cleanupState = Join-Path $repo 'build\v0.10.4-stale-v103-cleanup'
$recoveryDir = Join-Path $cleanupState 'recovery-before-cleanup'
$cleanupReport = Join-Path $cleanupState 'cleanup-result.json'
$utf8 = New-Object Text.UTF8Encoding($false)

# Exact live state captured by the preceding read-only inspector. Refuse to run
# if anything changed since that capture rather than guessing at a rollback.
$captured = [ordered]@{
    mapmenu = 'AE507D238F3DAB837FF8FE6D6CC43BF1DA3A39BD6233B2A3B51128F80869F28C'
    precisionchallenge = 'D4225CB9F3113928A219BF11B9AEE0D523A8205ACB245F47A9EF1088A7EE55E2'
    mapmaster = 'B930C51316CA136D9C40EA7CDA6A63A051127B357E97F1D4E4EB96A16993D96F'
    mapcoords = '945774DBC965F45AD78B8408BB1D2B10A527C6390E4E7C1190E8F2D7538DF3CB'
    compassgraph = 'D0ED78BA4B91813C74DC6088A8521D332EA991E760B1C2600D6EEEFC5FE60E68'
}

$oldMapBegin = '-- BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE'
$oldMapEnd = '-- END COMPLETIONIST V0.10.3 NATIVE RAVEN PRODUCTION BRIDGE'
$oldRavenBegin = '-- BEGIN COMPLETIONIST V0.10.3 NATIVE RAVEN LIFECYCLE BRIDGE'
$oldRavenEnd = '-- END COMPLETIONIST V0.10.3 NATIVE RAVEN LIFECYCLE BRIDGE'

function Hash-File([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Require-File([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing required file: $Path"
    }
}

function Require-Hash([string]$Path, [string]$Expected, [string]$Label) {
    $actual = Hash-File $Path
    if ($actual -ne $Expected.ToUpperInvariant()) {
        throw "$Label changed since the read-only inspection. Expected $Expected, got $actual. Refusing cleanup."
    }
}

function Count-Text([string]$Text, [string]$Needle) {
    if ([string]::IsNullOrEmpty($Needle)) { return 0 }
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

function Remove-ExactMarkerBlock([string]$Text, [string]$BeginMarker, [string]$EndMarker) {
    if ((Count-Text $Text $BeginMarker) -ne 1 -or (Count-Text $Text $EndMarker) -ne 1) {
        throw "Expected exactly one stale marker block: $BeginMarker"
    }

    $begin = $Text.IndexOf($BeginMarker, [StringComparison]::Ordinal)
    $endMarkerAt = $Text.IndexOf($EndMarker, [StringComparison]::Ordinal)
    if ($begin -lt 0 -or $endMarkerAt -lt $begin) {
        throw 'Stale marker block bounds are invalid.'
    }

    # Remove the entire marker lines and body, preserving every byte-equivalent
    # character outside that appended block.
    $start = $Text.LastIndexOf("`n", $begin)
    if ($start -lt 0) { $start = 0 } else { $start += 1 }

    $end = $Text.IndexOf("`n", $endMarkerAt + $EndMarker.Length)
    if ($end -lt 0) { $end = $Text.Length } else { $end += 1 }

    return $Text.Remove($start, $end - $start)
}

foreach ($p in @($candidateManifestPath, $dcbManifestPath, $mapBackup, $ravenBackup, $mapTarget, $ravenTarget)) {
    Require-File $p
}
foreach ($name in @('mapmaster.dcb','mapcoords.dcb','compassgraph.dcb')) {
    Require-File (Join-Path $dcbDir $name)
    Require-File (Join-Path $dcbBackupDir $name)
}

$candidate = Get-Content -LiteralPath $candidateManifestPath -Raw | ConvertFrom-Json
$dcbManifest = Get-Content -LiteralPath $dcbManifestPath -Raw | ConvertFrom-Json

if ([string]$candidate.candidate -ne 'Completionist_V103_Veithurgard_Raven_01' -or
    [string]$candidate.candidate_hash -ne 'E15E6BC82AE2773E') {
    throw 'Unexpected stale candidate manifest identity.'
}

Require-Hash $mapTarget $captured.mapmenu 'mapmenu.lua'
Require-Hash $ravenTarget $captured.precisionchallenge 'precisionchallenge.lua'
Require-Hash (Join-Path $dcbDir 'mapmaster.dcb') $captured.mapmaster 'mapmaster.dcb'
Require-Hash (Join-Path $dcbDir 'mapcoords.dcb') $captured.mapcoords 'mapcoords.dcb'
Require-Hash (Join-Path $dcbDir 'compassgraph.dcb') $captured.compassgraph 'compassgraph.dcb'

if ((Hash-File $mapBackup) -ne ([string]$candidate.map_before).ToUpperInvariant()) {
    throw 'Old mapmenu backup does not match the stale candidate manifest.'
}
if ((Hash-File $ravenBackup) -ne ([string]$candidate.raven_before).ToUpperInvariant()) {
    throw 'Old precisionchallenge backup does not match the stale candidate manifest.'
}
if ((Hash-File $ravenTarget) -ne ([string]$candidate.raven_after).ToUpperInvariant()) {
    throw 'precisionchallenge.lua is not exactly the stale candidate version; refusing whole-file restore.'
}

$mapText = [IO.File]::ReadAllText($mapTarget)
if ((Count-Text $mapText $oldMapBegin) -ne 1 -or (Count-Text $mapText $oldMapEnd) -ne 1) {
    throw 'Expected exactly one stale v0.10.3 map bridge.'
}
if ((Count-Text $mapText 'BEGIN COMPLETIONIST V0.10.4 RAVEN') -lt 1 -or
    (Count-Text $mapText 'goMapIconCompletionistRaven') -lt 1) {
    throw 'Later v0.10.4 Raven map work is not present; refusing surgical cleanup.'
}

$ravenText = [IO.File]::ReadAllText($ravenTarget)
if ((Count-Text $ravenText $oldRavenBegin) -ne 1 -or (Count-Text $ravenText $oldRavenEnd) -ne 1) {
    throw 'Expected exactly one stale v0.10.3 lifecycle bridge.'
}

# The current mapmaster is a later v0.10.4 artifact and MUST NOT be rolled back
# to the old v0.10.3 manifest. Only the two DCBs still exactly equal to the old
# candidate are restored.
foreach ($name in @('mapcoords.dcb','compassgraph.dcb')) {
    $stockExpected = ([string]$dcbManifest.stock_hashes.$name).ToUpperInvariant()
    $patchedExpected = ([string]$dcbManifest.patched_hashes.$name).ToUpperInvariant()
    $target = Join-Path $dcbDir $name
    $backup = Join-Path $dcbBackupDir $name
    if ((Hash-File $target) -ne $patchedExpected) {
        throw "$name is no longer the stale v0.10.3 patched file. Refusing cleanup."
    }
    if ((Hash-File $backup) -ne $stockExpected) {
        throw "$name stock backup hash mismatch."
    }
}

New-Item -ItemType Directory -Force -Path $recoveryDir | Out-Null
foreach ($pair in @(
    @($mapTarget, (Join-Path $recoveryDir 'mapmenu.lua')),
    @($ravenTarget, (Join-Path $recoveryDir 'precisionchallenge.lua')),
    @((Join-Path $dcbDir 'mapcoords.dcb'), (Join-Path $recoveryDir 'mapcoords.dcb')),
    @((Join-Path $dcbDir 'compassgraph.dcb'), (Join-Path $recoveryDir 'compassgraph.dcb')),
    @((Join-Path $dcbDir 'mapmaster.dcb'), (Join-Path $recoveryDir 'mapmaster-preserved.dcb'))
)) {
    Copy-Item -LiteralPath $pair[0] -Destination $pair[1] -Force
}

$before = [ordered]@{
    mapmenu = Hash-File $mapTarget
    precisionchallenge = Hash-File $ravenTarget
    mapmaster = Hash-File (Join-Path $dcbDir 'mapmaster.dcb')
    mapcoords = Hash-File (Join-Path $dcbDir 'mapcoords.dcb')
    compassgraph = Hash-File (Join-Path $dcbDir 'compassgraph.dcb')
}

try {
    $cleanMap = Remove-ExactMarkerBlock $mapText $oldMapBegin $oldMapEnd
    [IO.File]::WriteAllText($mapTarget, $cleanMap, $utf8)

    # This file is exactly the old candidate's post-install version, so restoring
    # its verified pre-install backup is safer than trying to edit Lua in place.
    Copy-Item -LiteralPath $ravenBackup -Destination $ravenTarget -Force

    foreach ($name in @('mapcoords.dcb','compassgraph.dcb')) {
        Copy-Item -LiteralPath (Join-Path $dcbBackupDir $name) -Destination (Join-Path $dcbDir $name) -Force
    }

    # Validate that later v0.10.4 map work survived and the old bridges are gone.
    $afterMapText = [IO.File]::ReadAllText($mapTarget)
    if ((Count-Text $afterMapText $oldMapBegin) -ne 0 -or (Count-Text $afterMapText $oldMapEnd) -ne 0) {
        throw 'Stale v0.10.3 map bridge survived cleanup.'
    }
    if ((Count-Text $afterMapText 'BEGIN COMPLETIONIST V0.10.4 RAVEN') -lt 1 -or
        (Count-Text $afterMapText 'goMapIconCompletionistRaven') -lt 1) {
        throw 'v0.10.4 Raven map work was lost during cleanup.'
    }

    $afterRavenText = [IO.File]::ReadAllText($ravenTarget)
    if ((Count-Text $afterRavenText $oldRavenBegin) -ne 0 -or (Count-Text $afterRavenText $oldRavenEnd) -ne 0) {
        throw 'Stale v0.10.3 lifecycle bridge survived cleanup.'
    }
    if ((Hash-File $ravenTarget) -ne ([string]$candidate.raven_before).ToUpperInvariant()) {
        throw 'precisionchallenge.lua did not restore to the verified pre-candidate hash.'
    }

    foreach ($name in @('mapcoords.dcb','compassgraph.dcb')) {
        if ((Hash-File (Join-Path $dcbDir $name)) -ne ([string]$dcbManifest.stock_hashes.$name).ToUpperInvariant()) {
            throw "$name did not restore to stock hash."
        }
    }
    if ((Hash-File (Join-Path $dcbDir 'mapmaster.dcb')) -ne $captured.mapmaster) {
        throw 'mapmaster.dcb changed even though cleanup must preserve the later v0.10.4 mapmaster.'
    }

    # Only after every file-level validation passes, retire the two stale active
    # manifests so new proof installers no longer treat the v0.10.3 candidate as active.
    $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')
    $retiredCandidate = Join-Path $candidateState ("retired-by-v104-cleanup-$stamp.json")
    $retiredDcb = Join-Path $dcbState ("retired-by-v104-cleanup-$stamp.json")
    Move-Item -LiteralPath $candidateManifestPath -Destination $retiredCandidate
    Move-Item -LiteralPath $dcbManifestPath -Destination $retiredDcb

    $after = [ordered]@{
        mapmenu = Hash-File $mapTarget
        precisionchallenge = Hash-File $ravenTarget
        mapmaster = Hash-File (Join-Path $dcbDir 'mapmaster.dcb')
        mapcoords = Hash-File (Join-Path $dcbDir 'mapcoords.dcb')
        compassgraph = Hash-File (Join-Path $dcbDir 'compassgraph.dcb')
    }

    $result = [ordered]@{
        result = 'STALE_V103_NATIVE_CANDIDATE_SURGICALLY_CLEANED'
        cleaned_utc = [DateTime]::UtcNow.ToString('o')
        game_process_running = $false
        save_state_written = $false
        progression_state_written = $false
        marker_state_written = $false
        mapmenu_old_bridge_removed = $true
        mapmenu_v104_raven_preserved = $true
        precisionchallenge_restored_to_verified_pre_candidate = $true
        mapcoords_restored_stock = $true
        compassgraph_restored_stock = $true
        mapmaster_preserved_untouched = $true
        retired_candidate_manifest = $retiredCandidate
        retired_dcb_manifest = $retiredDcb
        recovery_dir = $recoveryDir
        before = $before
        after = $after
    }
    [IO.File]::WriteAllText($cleanupReport, ($result | ConvertTo-Json -Depth 6), $utf8)

    Write-Host ''
    Write-Host 'Stale v0.10.3 native Raven candidate cleaned safely.'
    Write-Host '- old v0.10.3 map bridge removed only; later v0.10.4 Raven map code preserved'
    Write-Host '- precisionchallenge.lua restored to its verified pre-candidate version'
    Write-Host '- mapcoords.dcb and compassgraph.dcb restored to stock'
    Write-Host '- mapmaster.dcb left untouched at the later v0.10.4 hash'
    Write-Host '- stale candidate/DCB active manifests retired'
    Write-Host '- saves/progression/marker state touched: false'
    Write-Host ("- recovery snapshot: {0}" -f $recoveryDir)
} catch {
    Write-Warning 'Cleanup failed. Recovery snapshot was created before writes.'
    throw
}
