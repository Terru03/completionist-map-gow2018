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
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before building the Nornir lifecycle candidate.' }
if (Get-Process -Name GodOfWar -ErrorAction SilentlyContinue) { throw 'Close God of War before building the Nornir lifecycle candidate.' }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) { throw 'Python 3 is required.' }

$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$builder = Join-Path $PSScriptRoot 'build-nornir-lifecycle-offline.py'
$verticalState = Join-Path $repo 'build\v0.10.4-nornir-vertical-slice\offline'
$verticalReport = Join-Path $verticalState 'nornir-vertical-slice-offline.json'
$verticalRoot = Join-Path $verticalState 'candidate\game-root'
$archivedVertical = Join-Path $repo 'archive\field-logs\completionist-v104-nornir-vertical-slice-offline-success.json'
foreach ($required in @($verifyRaven, $builder, $verticalReport, $verticalRoot, $archivedVertical)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing required passing component: $required" }
}

$vertical = Get-Content -LiteralPath $verticalReport -Raw | ConvertFrom-Json
if ($vertical.result -ne 'NORNIR_VERTICAL_SLICE_OFFLINE_GATE_PASSED' -or
    -not $vertical.proof.complete_six_file_candidate -or
    -not $vertical.proof.dedicated_nornir_map_visual_bound -or
    -not $vertical.proof.dedicated_nornir_hud_capacity_two -or
    -not $vertical.proof.dedicated_nornir_compass_class_bound_to_hud_and_carrier -or
    -not $vertical.proof.dedicated_nornir_inworld_carrier_bound_to_hud -or
    -not $vertical.proof.runtime_proven_raven_edge_preserved -or
    -not $vertical.proof.live_raven_production_files_unchanged -or
    $vertical.safety.game_files_written -or
    $vertical.safety.runtime_install_performed -or
    $vertical.safety.save_state_written -or
    $vertical.safety.progression_state_written -or
    $vertical.safety.marker_state_written) {
    throw 'Existing Nornir vertical-slice report is not a passing offline source.'
}

$archived = Get-Content -LiteralPath $archivedVertical -Raw | ConvertFrom-Json
if ($archived.result -ne 'NORNIR_VERTICAL_SLICE_OFFLINE_GATE_PASSED' -or
    $archived.marker.id -ne '381B067F07254A25' -or
    $archived.resources.compass_class.uid -ne '8D5A770E0C4272CE' -or
    $archived.resources.map_visual.hash -ne 'E14C66C3B90633E0' -or
    $archived.resources.hud_visual.hash -ne '7DDC11175EBD1E94' -or
    $archived.resources.inworld_carrier.uid -ne '32BBE7E267644D93') {
    throw 'Archived Nornir vertical-slice success proof does not match the approved candidate identities.'
}

& $python.Source -m py_compile $builder
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed for Nornir lifecycle builder.' }

Write-Host 'Re-verifying frozen Raven production state before the Nornir lifecycle build...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verification failed.' }

$state = Join-Path $repo 'build\v0.10.4-nornir-lifecycle\offline'
$candidateDir = Join-Path $state 'candidate'
$report = Join-Path $state 'nornir-lifecycle-offline.json'
Remove-Item -LiteralPath $state -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $state | Out-Null

Write-Host ''
Write-Host 'Building Nornir native single-target mapmenu behavior plus real stock chest lifecycle OFFLINE...'
& $python.Source $builder `
    --game-root $GameRoot `
    --repo-root $repo `
    --vertical-slice-root $verticalRoot `
    --output-dir $candidateDir `
    --report $report
if ($LASTEXITCODE -ne 0) { throw 'Offline Nornir lifecycle builder failed.' }
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) { throw 'Nornir lifecycle report was not produced.' }

$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($proof.result -ne 'OFFLINE_NORNIR_LIFECYCLE_BUILT_AND_REPARSED' -or
    -not $proof.candidate.ten_file_candidate_complete -or
    -not $proof.source_game_and_loader_files_unchanged -or
    -not $proof.proof.frozen_raven_mapmenu_is_exact_prefix_of_candidate -or
    -not $proof.proof.old_synthetic_nornir_map_hud_path_retired -or
    -not $proof.proof.native_nornir_single_target_add_replace_remove_present -or
    -not $proof.proof.real_stock_nornir_lifecycle_bridge_present -or
    -not $proof.proof.all_six_binary_vertical_slice_files_copied_unchanged -or
    -not $proof.proof.no_save_progression_or_marker_state_mutation_authored -or
    $proof.runtime_ready -or
    -not $proof.ready_for_reversible_runtime_installer_gate -or
    $proof.safety.game_files_written -or
    $proof.safety.runtime_install_performed -or
    $proof.safety.save_state_written -or
    $proof.safety.progression_state_written -or
    $proof.safety.marker_state_written -or
    $proof.safety.raven_production_files_changed) {
    throw 'Nornir lifecycle report did not satisfy the strict offline gate.'
}

if ($proof.candidate.marker -ne 'Completionist_V104_Veithurgard_NornirChest_01' -or
    $proof.candidate.marker_id -ne '381B067F07254A25' -or
    $proof.candidate.compass_class.name -ne 'CompletionistNornirChest' -or
    $proof.candidate.compass_class.uid -ne '8D5A770E0C4272CE' -or
    $proof.candidate.map_visual.hash -ne 'E14C66C3B90633E0' -or
    $proof.candidate.hud_visual.hash -ne '7DDC11175EBD1E94' -or
    $proof.candidate.hud_visual.capacity -ne 2 -or
    $proof.candidate.inworld_carrier.uid -ne '32BBE7E267644D93') {
    throw 'Nornir lifecycle candidate identities changed.'
}

if (-not $proof.lifecycle_contract.runic_parent_challengeComplete_is_observed -or
    -not $proof.lifecycle_contract.runic_parent_restored_state_is_published_on_OnStart -or
    -not $proof.lifecycle_contract.actual_runic_loot_chest_OPENED_is_authoritative_collectible_completion -or
    -not $proof.lifecycle_contract.restored_opened_state_is_published_on_standard_chest_OnStart -or
    -not $proof.lifecycle_contract.challengeComplete_without_opened_keeps_parent_marker_visible -or
    -not $proof.lifecycle_contract.opened_suppresses_map_marker -or
    -not $proof.lifecycle_contract.opened_removes_active_native_compass_target -or
    $proof.lifecycle_contract.synthetic_progression_writes) {
    throw 'Nornir lifecycle semantics do not match the approved completion contract.'
}

if ($proof.components.mapmenu.source_sha256 -ne '67d069a798417b631c271f48c129fb2083591b81a31859ab94769fbbb8b01c6b' -or
    -not $proof.components.mapmenu.runtime_proven_raven_control_preserved -or
    -not $proof.components.mapmenu.native_nornir_add_replace_remove_logic_present -or
    -not $proof.components.mapmenu.stock_and_raven_replacement_paths_account_for_nornir -or
    -not $proof.components.mainhud.active_compass_hidden_on_authoritative_open -or
    -not $proof.components.runic.exact_inverse_to_clean_source -or
    -not $proof.components.standard.exact_inverse_to_clean_source) {
    throw 'Nornir Lua component proof is incomplete.'
}

$candidateRoot = Join-Path $candidateDir 'game-root'
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
foreach ($name in $expected.Keys) {
    $path = Join-Path $candidateRoot $expected[$name]
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Ten-file candidate missing: $name" }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($name -in @('r_ui.wad','wad_r_ui.dcb','wad_r_perm.dcb','mapmaster.dcb','mapcoords.dcb','compassgraph.dcb')) {
        $entry = $proof.candidate.six_binary_files.PSObject.Properties[$name]
    } else {
        $entry = $proof.candidate.four_lua_files.PSObject.Properties[$name]
    }
    if ($null -eq $entry) { throw "Ten-file report entry missing: $name" }
    $expectedSha = ([string]$entry.Value.sha256).ToLowerInvariant()
    if ($actual -ne $expectedSha) { throw "Ten-file candidate SHA mismatch: $name" }
}

Write-Host ''
Write-Host 'Re-verifying frozen Raven production state after the OFFLINE lifecycle build...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Raven production state changed during the Nornir lifecycle offline build.' }

Write-Host ''
Write-Host 'NORNIR_LIFECYCLE_OFFLINE_GATE_PASSED'
Write-Host '  marker: Completionist_V104_Veithurgard_NornirChest_01 / 381B067F07254A25'
Write-Host '  class: CompletionistNornirChest / 8D5A770E0C4272CE'
Write-Host '  map: goMapIconCompletionistNornirChest / E14C66C3B90633E0'
Write-Host '  HUD: goCompletionistNornirChestHUD / 7DDC11175EBD1E94 / capacity 2'
Write-Host '  in-world: COMPASS_INWORLD_COMPLETIONIST_NORNIR_CHEST / 32BBE7E267644D93'
Write-Host '  native Add/Replace/Remove behavior: authored offline'
Write-Host '  stock + Raven replacement paths account for Nornir: true'
Write-Host '  challengeComplete: observed and restored, but unlocked chest remains visible'
Write-Host '  actual Runic loot chest OPENED: authoritative collectible completion'
Write-Host '  OPENED -> map marker suppressed + active compass target removed'
Write-Host '  old synthetic Nornir map/HUD prototype retired: true'
Write-Host '  Raven production mapmenu preserved as exact prefix: true'
Write-Host '  ten-file candidate complete: true'
Write-Host '  game files written: false'
Write-Host '  saves/progression/marker state written: false'
Write-Host '  runtime install performed: false'
Write-Host "  candidate root: $candidateRoot"
Write-Host "  report: $report"
Write-Host ''
Write-Host 'Do not copy these files into God of War manually. If this gate passes, the next step is a transactional backup/rollback runtime installer and one controlled Veithurgard field test.'
