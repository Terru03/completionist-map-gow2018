param(
    [ValidateSet('Install', 'Remove')][string]$Mode = 'Install',
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before installing or removing the Raven HUD-art proof.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$dcbDir = Join-Path $game 'exec\dc\pc_le'
$permTarget = Join-Path $dcbDir 'wad_r_perm.dcb'
$rUiWad = Join-Path $game 'exec\wad\pc_le\r_ui.wad'
$rUiDcb = Join-Path $dcbDir 'wad_r_ui.dcb'
$ravenTexpack = Join-Path $game 'exec\patch\pc_le\completionist_v104_raven_map.texpack'

$stateDir = Join-Path $repo 'build\v0.10.4-packed-raven-hud-art-runtime'
$manifestPath = Join-Path $stateDir 'active.json'
$preparedReport = Join-Path $stateDir 'prepared.json'
$hudOutput = Join-Path $repo 'build\v0.10.4-packed-raven-hud-art\game-root\exec\dc\pc_le\wad_r_perm.dcb'
$builder = Join-Path $PSScriptRoot 'build-packed-raven-compass-hud-art-v1.py'

$baseInstaller = Join-Path $PSScriptRoot 'install-packed-raven-compass-class-proof.ps1'
$baseStateDir = Join-Path $repo 'build\v0.10.4-packed-raven-runtime'
$baseManifestPath = Join-Path $baseStateDir 'active.json'
$baseCandidate = Join-Path $repo 'build\v0.10.4-packed-raven-compass-class\game-root\exec\dc\pc_le\wad_r_perm.dcb'
$utf8 = New-Object Text.UTF8Encoding($false)

$expectedRUiWad = '9EB1F548DE036EB56C031561A9B7665D71B54FE251D360D2A5B7C60E3D6FF3C3'
$expectedRUiDcb = 'B8D5627416787AE6761E0212A1E8DE56E33ABE7C251DB838C4AF20A00AFC161B'
$expectedRavenTexpack = '648A16A6FABD526B56C031561A9C5F983B5257296E28081C81EDAFB8790A1C6A7'
$expectedHudHash = '584F31DC8BD6E738'
$expectedDockInWorld = '0E24C47DE2F769CA'

function Hash-File([string]$Path) {
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

if ($Mode -eq 'Remove') {
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        if (Test-Path -LiteralPath $baseManifestPath -PathType Leaf) {
            throw 'HUD-art manifest is missing but the underlying packed-class proof is still active. Refusing to guess rollback ownership.'
        }
        Write-Host 'Raven HUD-art proof is already removed.'
        return
    }
    if (-not (Test-Path -LiteralPath $baseManifestPath -PathType Leaf)) {
        throw 'Underlying packed-class manifest is missing. Refusing an unrelated rollback.'
    }

    & $baseInstaller -Mode Remove -GameRoot $GameRoot
    if ($LASTEXITCODE -ne 0) { throw 'Underlying packed-class rollback failed.' }

    $removed = Join-Path $stateDir ('removed-' + [Guid]::NewGuid().ToString('N') + '.json')
    Move-Item -LiteralPath $manifestPath -Destination $removed
    Write-Host 'Raven HUD-art proof removed.'
    Write-Host '- proven pre-proof v0.10.4 DCB/mapmenu baseline restored byte-for-byte'
    Write-Host '- solved Raven map WAD/DCB/texpack were never modified by this proof'
    return
}

if (Test-Path -LiteralPath $manifestPath -PathType Leaf) {
    throw 'Raven HUD-art proof is already installed.'
}
if (Test-Path -LiteralPath $baseManifestPath -PathType Leaf) {
    throw 'Underlying packed Raven class proof is already active. Remove/collect it before the HUD-art proof.'
}
foreach ($path in @($builder, $baseInstaller, $permTarget, $rUiWad, $rUiDcb, $ravenTexpack)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing required file: $path" }
}

# The HUD proof reuses the existing, already-working Raven GameObject/material/texture
# chain. It must not rebuild or overwrite any of these solved map-art resources.
if ((Hash-File $rUiWad) -ne $expectedRUiWad) {
    throw 'r_ui.wad differs from the proven resident-partial-linearization Raven map-art WAD. Refusing HUD proof.'
}
if ((Hash-File $rUiDcb) -ne $expectedRUiDcb) {
    throw 'wad_r_ui.dcb differs from the proven Raven map-art registration DCB. Refusing HUD proof.'
}
if ((Hash-File $ravenTexpack) -ne $expectedRavenTexpack) {
    throw 'completionist_v104_raven_map.texpack differs from the proven Raven artwork texpack. Refusing HUD proof.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }
New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path $hudOutput -Parent) | Out-Null

Write-Host 'Building HUD-only CompletionistRaven candidate from the proven UID-sorted class...'
& $python.Source $builder --game-root $game --output $hudOutput --report $preparedReport
if ($LASTEXITCODE -ne 0) { throw 'HUD-only Raven candidate build failed.' }
if (-not (Test-Path -LiteralPath $preparedReport -PathType Leaf)) { throw 'HUD candidate report missing.' }
$hud = Get-Content -LiteralPath $preparedReport -Raw | ConvertFrom-Json
if ([string]$hud.result -ne 'OFFLINE_PACKED_COMPLETIONIST_RAVEN_HUD_ART_BUILT' -or
    $hud.game_files_written -ne $false -or
    $hud.installed -ne $false -or
    $hud.save_progression_marker_state_written -ne $false -or
    [string]$hud.class.name -ne 'CompletionistRaven' -or
    [string]$hud.class.uid -ne '5DC46967D3095F7E' -or
    [string]$hud.class.root -ne '0x4E2C50' -or
    $hud.class.export_uid_order_strictly_increasing -ne $true -or
    [string]$hud.visual_isolation.hud_IconName_after -ne $expectedHudHash -or
    [string]$hud.visual_isolation.InWorld_tMPIcon_Name -ne $expectedDockInWorld -or
    $hud.visual_isolation.changed_bytes_confined_to_raven_IconName -ne $true -or
    $hud.visual_isolation.real_DockPoint_record_byte_identical -ne $true) {
    throw 'HUD-only Raven candidate report failed validation.'
}
$hudHash = ([string]$hud.candidate_sha256).ToUpperInvariant()
$baseRegistrationHash = ([string]$hud.base_registration_candidate_sha256).ToUpperInvariant()
if ((Hash-File $hudOutput) -ne $hudHash) { throw 'HUD candidate file hash mismatch.' }

# Reuse the already-proven class proof installer for mapcoords/compassgraph,
# mapmenu bridge, backups and rollback. It first installs the known-good class
# that still clones DockPoint visuals.
Write-Host 'Installing the proven UID-sorted class/navigation baseline...'
& $baseInstaller -Mode Install -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Underlying packed-class install failed.' }
if (-not (Test-Path -LiteralPath $baseManifestPath -PathType Leaf)) {
    throw 'Underlying packed-class manifest was not created.'
}
if (-not (Test-Path -LiteralPath $baseCandidate -PathType Leaf)) {
    throw 'Underlying packed-class candidate is missing after install.'
}

$originalBaseManifestText = [IO.File]::ReadAllText($baseManifestPath)
$baseManifest = $originalBaseManifestText | ConvertFrom-Json
$installedBaseHash = Hash-File $permTarget
$manifestBaseHash = ([string]$baseManifest.patched_hashes.'wad_r_perm.dcb').ToUpperInvariant()
if ($installedBaseHash -ne $baseRegistrationHash -or $manifestBaseHash -ne $baseRegistrationHash) {
    try { & $baseInstaller -Mode Remove -GameRoot $GameRoot } catch { }
    throw "Underlying registration candidate hash differs from HUD builder base. Installed=$installedBaseHash expected=$baseRegistrationHash"
}
if ((Hash-File $baseCandidate) -ne $baseRegistrationHash) {
    try { & $baseInstaller -Mode Remove -GameRoot $GameRoot } catch { }
    throw 'Underlying candidate backup path does not match the proven registration candidate.'
}

# Prepare the rollback manifest to recognize the HUD candidate before exposing it
# as the active installed proof. If anything fails, restore the known-good base
# candidate + original manifest, then invoke the base rollback.
$baseManifest.patched_hashes.'wad_r_perm.dcb' = $hudHash
$baseManifest.candidate_wad_sha256 = $hudHash
$visualMeta = [ordered]@{
    proof = 'v0.10.4-packed-raven-hud-art-v1'
    hud_icon_name = 'goMapIconCompletionistRaven'
    hud_icon_hash = $expectedHudHash
    inworld_hash = $expectedDockInWorld
    inworld_intentionally_dock_for_isolation = $true
    base_registration_candidate_sha256 = $baseRegistrationHash
}
$baseManifest | Add-Member -NotePropertyName hud_visual_proof -NotePropertyValue $visualMeta -Force
$updatedBaseManifestText = $baseManifest | ConvertTo-Json -Depth 10

try {
    Copy-Item -LiteralPath $hudOutput -Destination $permTarget -Force
    if ((Hash-File $permTarget) -ne $hudHash) { throw 'Installed HUD candidate hash mismatch.' }

    [IO.File]::WriteAllText($baseManifestPath, $updatedBaseManifestText, $utf8)
    $roundTrip = Get-Content -LiteralPath $baseManifestPath -Raw | ConvertFrom-Json
    if (([string]$roundTrip.patched_hashes.'wad_r_perm.dcb').ToUpperInvariant() -ne $hudHash) {
        throw 'Updated underlying rollback manifest did not retain HUD candidate hash.'
    }

    $manifest = [ordered]@{
        proof = 'v0.10.4-packed-raven-hud-art-v1'
        candidate = 'Completionist_V103_Veithurgard_Raven_01'
        candidate_hash = 'E15E6BC82AE2773E'
        compass_class = 'CompletionistRaven'
        compass_class_uid = '5DC46967D3095F7E'
        compass_class_root = '0x4E2C50'
        base_registration_candidate_sha256 = $baseRegistrationHash
        hud_candidate_sha256 = $hudHash
        hud_IconName = $expectedHudHash
        hud_resource = 'goMapIconCompletionistRaven'
        InWorld_tMPIcon_Name = $expectedDockInWorld
        expected_hud_visual = 'Raven'
        expected_inworld_visual = 'DockPoint'
        expected_map_visual = 'Raven unchanged'
        raven_map_r_ui_wad_sha256 = $expectedRUiWad
        raven_map_r_ui_dcb_sha256 = $expectedRUiDcb
        raven_texpack_sha256 = $expectedRavenTexpack
        writes_save_state = $false
        writes_progression_state = $false
        writes_marker_state = $false
        modifies_real_docks = $false
        modifies_raven_map_resources = $false
        installed_utc = [DateTime]::UtcNow.ToString('o')
    }
    [IO.File]::WriteAllText($manifestPath, ($manifest | ConvertTo-Json -Depth 8), $utf8)
} catch {
    $failure = $_
    try {
        Copy-Item -LiteralPath $baseCandidate -Destination $permTarget -Force
        [IO.File]::WriteAllText($baseManifestPath, $originalBaseManifestText, $utf8)
        if (Test-Path -LiteralPath $manifestPath -PathType Leaf) { Remove-Item -LiteralPath $manifestPath -Force }
        & $baseInstaller -Mode Remove -GameRoot $GameRoot
    } catch {
        Write-Warning "Automatic recovery after HUD install failure also failed: $($_.Exception.Message)"
    }
    throw $failure
}

Write-Host ''
Write-Host 'Completionist Map v0.10.4 HUD-ONLY Raven compass artwork proof installed.'
Write-Host '- CompletionistRaven native registration remains the proven UID-sorted packed class'
Write-Host '- HUD IconName now points to existing goMapIconCompletionistRaven (584F31DC8BD6E738)'
Write-Host '- floating in-world marker intentionally remains COMPASS_INWORLD_DOCK for isolation'
Write-Host '- solved Raven map WAD/DCB/texpack were validated and left untouched'
Write-Host '- real DockPoint class/resources were left untouched'
Write-Host '- installer never calls ShowMarker and never writes save/progression/marker state'
Write-Host ''
Write-Host 'Launch GoW, load Veithurgard, select the Raven on the map and Add to Compass once.'
Write-Host 'Expected: map Raven stays Raven; compass HUD becomes Raven; floating in-world marker stays DockPoint.'
Write-Host 'Then close GoW and run collect-packed-raven-hud-art-proof.ps1.'
Write-Host ("Emergency rollback: powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"{0}`" -Mode Remove" -f $PSCommandPath)
