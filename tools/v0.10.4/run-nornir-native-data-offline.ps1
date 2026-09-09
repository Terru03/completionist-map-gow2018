param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/v104-raven-production'
$ExpectedAnchor = '45DE535858C63212'
$ExpectedMarker = 'Completionist_V104_Veithurgard_NornirChest_01'
$ExpectedMarkerId = '381B067F07254A25'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$VerifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$Builder = Join-Path $PSScriptRoot 'build-nornir-native-data-offline.py'
$Observed = Join-Path $RepoRoot 'data\observed\veithurgard-nornir-breakable-v0.8.json'
$Topology = Join-Path $RepoRoot 'build\v0.10.4-nornir-native-anchor\veithurgard-nornir-topology.json'
$StateDir = Join-Path $RepoRoot 'build\v0.10.4-nornir-native-candidate\offline'
$CandidateDir = Join-Path $StateDir 'candidate'
$Report = Join-Path $StateDir 'nornir-native-data.json'

$branch = (& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $ExpectedBranch) {
    throw "Expected Git branch '$ExpectedBranch', found '$branch'."
}

$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -eq 'GoW' -or $_.ProcessName -eq 'GodOfWar'
})
if ($running.Count -gt 0) {
    throw 'God of War is running. Close it before the offline Nornir native-data build.'
}

foreach ($required in @($VerifyRaven, $Builder, $Observed, $Topology)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing required file: $required"
    }
}

$topologyProof = Get-Content -LiteralPath $Topology -Raw | ConvertFrom-Json
if ([string]$topologyProof.result -ne 'NATIVE_ROUTE_ANCHOR_TOPOLOGY_READ_ONLY' -or
    $topologyProof.game_files_written -ne $false -or
    $topologyProof.saves_progression_marker_state_written -ne $false -or
    $topologyProof.runtime_proven_raven_reference.edge_verified -ne $true) {
    throw 'Existing Nornir topology report does not satisfy the read-only Raven-reference contract.'
}
$selected = [string]$topologyProof.'provisional_same-type_nearest_candidate'
if ($selected -ne $ExpectedAnchor) {
    throw "Topology-selected helper changed: expected $ExpectedAnchor, found $selected"
}
$candidate = @($topologyProof.candidate_ranking | Where-Object { [string]$_.id -eq $ExpectedAnchor })
if ($candidate.Count -ne 1 -or
    $candidate[0].same_helper_type_as_raven_anchor -ne $true -or
    $candidate[0].same_graph_component_as_raven_anchor -ne $true) {
    throw 'Selected Nornir helper no longer satisfies the proven Raven topology criteria.'
}

Write-Host 'Re-verifying frozen Raven production state before offline Nornir native-data build...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $VerifyRaven -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) {
    throw 'Raven production verification failed; refusing Nornir offline build.'
}

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) { throw 'Python 3 is required.' }

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

Write-Host ''
Write-Host 'Building a Nornir native-data candidate outside the game directory...'
& $python.Source $Builder `
    --game-root $GameRoot `
    --repo-root $RepoRoot `
    --observed $Observed `
    --output-dir $CandidateDir `
    --report $Report
if ($LASTEXITCODE -ne 0) {
    throw 'Offline Nornir native-data builder failed.'
}
if (-not (Test-Path -LiteralPath $Report -PathType Leaf)) {
    throw 'Offline Nornir builder did not create its report.'
}

$proof = Get-Content -LiteralPath $Report -Raw | ConvertFrom-Json
if ([string]$proof.result -ne 'OFFLINE_NORNIR_NATIVE_DATA_BUILT_AND_REPARSED' -or
    [string]$proof.candidate.name -ne $ExpectedMarker -or
    [string]$proof.candidate.id -ne $ExpectedMarkerId -or
    [string]$proof.candidate.selected_graph_neighbor -ne $ExpectedAnchor -or
    $proof.source_game_files_unchanged -ne $true -or
    $proof.reparse_verification.runtime_proven_raven_edge_preserved -ne $true -or
    $proof.reparse_verification.preexisting_map_markers_semantically_identical -ne $true -or
    $proof.reparse_verification.preexisting_mapcoords_semantically_identical -ne $true -or
    $proof.reparse_verification.preexisting_compass_helpers_identical -ne $true -or
    $proof.reparse_verification.preexisting_compass_edges_identical_and_ordered -ne $true -or
    $proof.reparse_verification.unresolved_graph_endpoints -ne 0 -or
    $proof.game_files_written -ne $false -or
    $proof.saves_progression_marker_state_written -ne $false -or
    $proof.runtime_install_performed -ne $false -or
    $proof.runtime_ready -ne $false) {
    throw 'Offline Nornir report did not satisfy the strict native-data proof contract.'
}

Write-Host ''
Write-Host 'NORNIR_NATIVE_DATA_OFFLINE_GATE_PASSED'
Write-Host "  marker:          $($proof.candidate.name)"
Write-Host "  id:              $($proof.candidate.id)"
Write-Host ("  world:           {0}, {1}, {2}" -f $proof.candidate.world_position[0], $proof.candidate.world_position[1], $proof.candidate.world_position[2])
Write-Host "  graph neighbour: $($proof.candidate.selected_graph_neighbor)"
Write-Host "  helper type:     $($proof.selected_anchor.helper_type)"
Write-Host "  helper distance: $($proof.selected_anchor.distance_to_chest_metres)m"
Write-Host '  Raven native data preserved: true'
Write-Host '  all pre-existing markers/coords/helpers/edges preserved: true'
Write-Host '  unresolved graph endpoints: 0'
Write-Host '  temporary map art: Raven visual, OFFLINE STRUCTURAL PROOF ONLY'
Write-Host '  game files written: false'
Write-Host '  runtime install performed: false'
Write-Host "  source mapmaster SHA256: $($proof.source_hashes_before.'mapmaster.dcb')"
Write-Host "  candidate mapmaster SHA256: $($proof.generated_files.'mapmaster.dcb'.sha256)"
Write-Host "  candidate mapcoords SHA256: $($proof.generated_files.'mapcoords.dcb'.sha256)"
Write-Host "  candidate compassgraph SHA256: $($proof.generated_files.'compassgraph.dcb'.sha256)"
Write-Host "  report: $Report"
Write-Host ''
Write-Host 'Do not install this candidate. Next gate is dedicated CompletionistNornirChest map/HUD/in-world art plus compass class.'
