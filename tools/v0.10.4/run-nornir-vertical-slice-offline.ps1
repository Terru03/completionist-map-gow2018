param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedBranch = 'codex/v104-raven-production'
$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not determine current Git branch.' }
if ($branch -ne $expectedBranch) { throw "Expected branch '$expectedBranch', got '$branch'." }
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before building the Nornir vertical slice.' }
if (Get-Process -Name GodOfWar -ErrorAction SilentlyContinue) { throw 'Close God of War before building the Nornir vertical slice.' }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) { throw 'Python 3 is required.' }

$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$nativeRunner = Join-Path $PSScriptRoot 'run-nornir-native-data-offline.ps1'
$mapHudRunner = Join-Path $PSScriptRoot 'run-nornir-map-hud-offline.ps1'
$permBuilder = Join-Path $PSScriptRoot 'build-nornir-perm-offline.py'
$assembler = Join-Path $PSScriptRoot 'assemble-nornir-vertical-slice-offline.py'
foreach ($required in @($verifyRaven, $nativeRunner, $mapHudRunner, $permBuilder, $assembler)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required tool: $required" }
}

& $python.Source -m py_compile $permBuilder $assembler
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed for the Nornir vertical-slice tools.' }

Write-Host 'Re-verifying frozen Raven production state before Nornir vertical-slice assembly...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verification failed.' }

Write-Host ''
Write-Host 'Refreshing the strict OFFLINE Nornir native-data candidate...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $nativeRunner -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Nornir native-data offline gate failed.' }

Write-Host ''
Write-Host 'Refreshing the strict OFFLINE Nornir map/HUD candidate...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $mapHudRunner -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Nornir map/HUD offline gate failed.' }

$nativeState = Join-Path $repo 'build\v0.10.4-nornir-native-candidate\offline'
$nativeDir = Join-Path $nativeState 'candidate\game-root\exec\dc\pc_le'
$nativeReport = Join-Path $nativeState 'nornir-native-data.json'
$mapHudDir = Join-Path $repo 'build\v0.10.4-nornir-map-hud\offline'
$mapHudReport = Join-Path $mapHudDir 'nornir-map-hud-offline.json'
foreach ($required in @($nativeDir, $nativeReport, $mapHudDir, $mapHudReport)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Required passing component missing: $required" }
}

$state = Join-Path $repo 'build\v0.10.4-nornir-vertical-slice\offline'
$componentDir = Join-Path $state 'components'
$permCandidate = Join-Path $componentDir 'wad_r_perm.dcb'
$permReport = Join-Path $componentDir 'nornir-perm-offline.json'
$assemblyDir = Join-Path $state 'candidate'
$report = Join-Path $state 'nornir-vertical-slice-offline.json'
Remove-Item -LiteralPath $state -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $componentDir | Out-Null

Write-Host ''
Write-Host 'Building CompletionistNornirChest plus its dedicated in-world carrier OFFLINE...'
& $python.Source $permBuilder `
    --game-root $GameRoot `
    --output $permCandidate `
    --report $permReport
if ($LASTEXITCODE -ne 0) { throw 'Offline Nornir perm builder failed.' }
if (-not (Test-Path -LiteralPath $permReport -PathType Leaf)) { throw 'Nornir perm report was not produced.' }

$perm = Get-Content -LiteralPath $permReport -Raw | ConvertFrom-Json
if ($perm.result -ne 'OFFLINE_NORNIR_PERM_BUILT_AND_REPARSED' -or
    -not $perm.ready_for_vertical_slice_assembly -or
    $perm.runtime_ready -or
    -not $perm.proof.candidate_data_normalizes_exactly_to_raven_production -or
    -not $perm.proof.frozen_raven_class_preserved -or
    -not $perm.proof.frozen_raven_inworld_preserved -or
    -not $perm.proof.stock_DockPoint_resources_preserved_by_exact_normalization -or
    $perm.safety.game_files_written -or
    $perm.safety.runtime_install_performed -or
    $perm.safety.save_state_written -or
    $perm.safety.progression_state_written -or
    $perm.safety.marker_state_written) {
    throw 'Nornir perm candidate did not satisfy the strict offline proof contract.'
}
if ($perm.nornir_class.name -ne 'CompletionistNornirChest' -or
    $perm.nornir_class.uid -ne '8D5A770E0C4272CE' -or
    $perm.nornir_class.type_id -ne '0x11E' -or
    $perm.nornir_class.IconName -ne '7DDC11175EBD1E94' -or
    $perm.nornir_class.InWorld_tMPIcon_Name -ne '32BBE7E267644D93' -or
    $perm.nornir_inworld.name -ne 'COMPASS_INWORLD_COMPLETIONIST_NORNIR_CHEST' -or
    $perm.nornir_inworld.uid -ne '32BBE7E267644D93' -or
    $perm.nornir_inworld.type_id -ne '0x129' -or
    $perm.nornir_inworld.IconName -ne '7DDC11175EBD1E94') {
    throw 'Nornir perm identities/bindings do not match the approved vertical-slice plan.'
}
if ((Get-FileHash -LiteralPath $permCandidate -Algorithm SHA256).Hash.ToLowerInvariant() -ne ([string]$perm.candidate_sha256).ToLowerInvariant()) {
    throw 'Nornir perm candidate SHA does not match its proof report.'
}

Write-Host ''
Write-Host 'Assembling the complete six-file Nornir vertical slice OFFLINE...'
& $python.Source $assembler `
    --game-root $GameRoot `
    --repo-root $repo `
    --native-dir $nativeDir `
    --native-report $nativeReport `
    --map-hud-dir $mapHudDir `
    --map-hud-report $mapHudReport `
    --perm-candidate $permCandidate `
    --perm-report $permReport `
    --output-dir $assemblyDir `
    --report $report
if ($LASTEXITCODE -ne 0) { throw 'Offline Nornir vertical-slice assembler failed.' }
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) { throw 'Nornir vertical-slice report was not produced.' }

$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($proof.result -ne 'NORNIR_VERTICAL_SLICE_OFFLINE_GATE_PASSED' -or
    -not $proof.ready_for_mapmenu_lifecycle_offline_gate -or
    $proof.runtime_ready -or
    -not $proof.proof.complete_six_file_candidate -or
    -not $proof.proof.dedicated_nornir_map_visual_bound -or
    -not $proof.proof.dedicated_nornir_hud_capacity_two -or
    -not $proof.proof.dedicated_nornir_compass_class_bound_to_hud_and_carrier -or
    -not $proof.proof.dedicated_nornir_inworld_carrier_bound_to_hud -or
    -not $proof.proof.nornir_native_coordinate_and_graph_edge_reparsed -or
    -not $proof.proof.runtime_proven_raven_edge_preserved -or
    -not $proof.proof.frozen_raven_class_and_carrier_preserved_by_perm_normalization -or
    -not $proof.proof.frozen_raven_map_hud_resources_preserved_by_ui_normalization -or
    -not $proof.proof.stock_DockPoint_resources_preserved_by_component_normalization -or
    -not $proof.proof.mapmaster_retarget_exactly_reversible -or
    -not $proof.proof.live_raven_production_files_unchanged -or
    $proof.safety.game_files_written -or
    $proof.safety.runtime_install_performed -or
    $proof.safety.save_state_written -or
    $proof.safety.progression_state_written -or
    $proof.safety.marker_state_written) {
    throw 'Final Nornir vertical-slice report did not satisfy the strict offline gate.'
}

$candidateRoot = Join-Path $assemblyDir 'game-root'
$dcCandidate = Join-Path $candidateRoot 'exec\dc\pc_le'
$wadCandidate = Join-Path $candidateRoot 'exec\wad\pc_le'
$expectedPaths = @{
    'r_ui.wad' = Join-Path $wadCandidate 'r_ui.wad'
    'wad_r_ui.dcb' = Join-Path $dcCandidate 'wad_r_ui.dcb'
    'wad_r_perm.dcb' = Join-Path $dcCandidate 'wad_r_perm.dcb'
    'mapmaster.dcb' = Join-Path $dcCandidate 'mapmaster.dcb'
    'mapcoords.dcb' = Join-Path $dcCandidate 'mapcoords.dcb'
    'compassgraph.dcb' = Join-Path $dcCandidate 'compassgraph.dcb'
}
foreach ($name in $expectedPaths.Keys) {
    $path = $expectedPaths[$name]
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Final candidate file missing: $name" }
    $fileProperty = $proof.candidate.files.PSObject.Properties[$name]
    if ($null -eq $fileProperty) { throw "Final candidate report entry missing: $name" }
    $fileProof = $fileProperty.Value
    $actualSha = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    $expectedSha = ([string]$fileProof.sha256).ToLowerInvariant()
    if ($actualSha -ne $expectedSha) { throw "Final candidate SHA mismatch: $name" }
}

Write-Host ''
Write-Host 'Re-verifying frozen Raven production state after the complete OFFLINE build...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Raven production state changed during the Nornir offline vertical-slice build.' }

Write-Host ''
Write-Host 'NORNIR_VERTICAL_SLICE_OFFLINE_GATE_PASSED'
Write-Host '  CompletionistNornirChest: 8D5A770E0C4272CE / type 0x11E'
Write-Host '  HUD: 7DDC11175EBD1E94 / GOPool capacity 2'
Write-Host '  in-world carrier: 32BBE7E267644D93 / type 0x129'
Write-Host '  map: goMapIconCompletionistNornirChest / E14C66C3B90633E0'
Write-Host '  marker: Completionist_V104_Veithurgard_NornirChest_01 / 381B067F07254A25'
Write-Host '  graph neighbour: 45DE535858C63212'
Write-Host '  six-file candidate complete: true'
Write-Host '  mapmaster retarget exact inverse proof: true'
Write-Host '  Raven production semantics preserved: true'
Write-Host '  stock DockPoint resources preserved: true'
Write-Host '  game files written: false'
Write-Host '  saves/progression/marker state written: false'
Write-Host '  runtime install performed: false'
Write-Host "  candidate root: $candidateRoot"
Write-Host "  report: $report"
Write-Host ''
Write-Host 'Do not copy these files into God of War yet. Next gate is Nornir single-target mapmenu behavior plus real chest-completion lifecycle, still OFFLINE.'
