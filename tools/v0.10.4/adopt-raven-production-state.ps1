param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/v104-raven-production'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Verify = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$StateDir = Join-Path $RepoRoot 'build\v0.10.4-raven-production'
$Report = Join-Path $StateDir 'production-state.json'
$Manifest = Join-Path $StateDir 'active.json'

$branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) {
    throw "Expected Git branch '$ExpectedBranch', found '$branch'."
}

$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -eq 'GoW' -or $_.ProcessName -eq 'GodOfWar'
})
if ($running.Count -gt 0) {
    throw 'God of War is running. Close it before adopting the production baseline.'
}

if (-not (Test-Path -LiteralPath $Verify -PathType Leaf)) { throw "Missing verifier wrapper: $Verify" }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Verify -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Production verification failed; refusing adoption.' }

$proof = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'RAVEN_PRODUCTION_STATE_VERIFIED' -or
    $proof.ready_to_adopt_as_production_baseline -ne $true) {
    throw 'Production verifier report is not adoptable.'
}

$researchManifests = [ordered]@{
    custom_class = 'build/v0.10.4-raven-native-custom-class-control/active.json'
    single_active = 'build/v0.10.4-raven-single-active-compass-control/active.json'
    gopool_registration = 'build/v0.10.4-raven-compass-hud-gopool-registration/active-install.json'
    inworld_carrier = 'build/v0.10.4-raven-inworld-carrier/runtime/active.json'
    capacity2 = 'build/v0.10.4-raven-hud-gopool-capacity2-control/runtime/active.json'
}

$adopted = [ordered]@{
    kind = 'completionist-v104-raven-production-baseline'
    schema = 1
    status = 'adopted'
    branch = $ExpectedBranch
    adopted_utc = [DateTime]::UtcNow.ToString('o')
    marker = 'Completionist_V103_Veithurgard_Raven_01'
    compass_class = 'CompletionistRaven'
    map_visual = [ordered]@{
        name = 'goMapIconCompletionistRaven'
        hash = '584F31DC8BD6E738'
        gopool_capacity = 1
    }
    hud_visual = [ordered]@{
        name = 'goCompletionistRavenHUD'
        hash = '45E5C7943749F81C'
        gopool_index = 256
        gopool_capacity = 2
    }
    inworld_carrier = [ordered]@{
        name = 'COMPASS_INWORLD_COMPLETIONIST_RAVEN'
        uid = '21DC5A7D4AD17628'
        type_id = '0x129'
    }
    live_hashes = $proof.live_hashes
    canonical_native_data = [ordered]@{
        mapcoords_sha256 = '945774dbc965f45ad78b8408bb1d2b10a527c6390e4e7c1190e8f2d7538df3cb'
        compassgraph_sha256 = 'd0ed78ba4b91813c74dc6088a8521d332ea991e760b1c2600d6eeefc5fe60e68'
    }
    runtime_invariants = [ordered]@{
        crash_free = $true
        custom_map_art = $true
        custom_compass_hud_art = $true
        custom_inworld_art = $true
        native_distance = $true
        native_pathfinding = $true
        single_active_target = $true
        add_replace_remove = $true
    }
    verifier_report = $Report
    runtime_proof = 'archive/field-logs/completionist-v104-raven-full-compass-runtime-success.json'
    research_manifests_adopted = $researchManifests
    game_files_written_by_adoption = $false
    saves_progression_marker_state_written = $false
    next_family_gate = 'Clone this architecture through data/native-markers/schema.json; do not weaken Raven invariants while adding another family.'
}

$json = $adopted | ConvertTo-Json -Depth 12
if (Test-Path -LiteralPath $Manifest -PathType Leaf) {
    $existing = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json
    if ([string]$existing.kind -ne 'completionist-v104-raven-production-baseline' -or $existing.schema -ne 1) {
        throw "Unexpected production manifest already exists: $Manifest"
    }
    $oldPerm = ([string]$existing.live_hashes.'wad_r_perm.dcb').ToLowerInvariant()
    $newPerm = ([string]$proof.live_hashes.'wad_r_perm.dcb').ToLowerInvariant()
    $oldUi = ([string]$existing.live_hashes.'wad_r_ui.dcb').ToLowerInvariant()
    $newUi = ([string]$proof.live_hashes.'wad_r_ui.dcb').ToLowerInvariant()
    if ($oldPerm -ne $newPerm -or $oldUi -ne $newUi) {
        throw 'Existing adopted production manifest describes different live DCB hashes.'
    }
    Write-Host 'Raven production baseline is already adopted and matches the live state.'
    Write-Host "  manifest: $Manifest"
    exit 0
}

[IO.File]::WriteAllText($Manifest, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))

Write-Host ''
Write-Host 'RAVEN_PRODUCTION_BASELINE_ADOPTED'
Write-Host '  current proven game files rewritten: false'
Write-Host '  research layers consolidated logically: true'
Write-Host '  Raven runtime invariants frozen: true'
Write-Host "  manifest: $Manifest"
Write-Host ''
Write-Host 'Next target: add the next collectible family from the native-marker schema without changing the proven Raven contract.'
