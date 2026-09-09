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
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before building the Nornir map/HUD candidate.' }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }
$verify = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$builder = Join-Path $PSScriptRoot 'build-nornir-map-hud-offline-v4.py'
foreach ($required in @($verify, $builder)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required tool: $required" }
}

Write-Host 'Re-verifying frozen Raven production state before cloning the Nornir map/HUD resources...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verify -GameRoot $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verification failed.' }

$topologyReport = Join-Path $repo 'build\v0.10.4-nornir-resource-topology\nornir-resource-topology.json'
if (-not (Test-Path -LiteralPath $topologyReport -PathType Leaf)) { throw "Nornir resource topology report missing: $topologyReport" }
$topology = Get-Content -LiteralPath $topologyReport -Raw | ConvertFrom-Json
if ($topology.result -ne 'NORNIR_RESOURCE_TOPOLOGY_VERIFIED' -or -not $topology.ready_for_nornir_resource_builder) {
    throw 'Nornir resource topology gate is not builder-ready.'
}
if ($topology.planned_nornir.gopool_plan.current_rows -ne 257 -or
    $topology.planned_nornir.gopool_plan.map_row_index -ne 257 -or
    $topology.planned_nornir.gopool_plan.hud_row_index -ne 258 -or
    $topology.planned_nornir.gopool_plan.resulting_rows -ne 259) {
    throw 'Nornir GOPool topology plan changed.'
}

$artReport = Join-Path $repo 'build\v0.10.4-nornir-resident-art\offline\nornir-resident-art.json'
if (-not (Test-Path -LiteralPath $artReport -PathType Leaf)) { throw "Nornir resident-art report missing: $artReport" }
$art = Get-Content -LiteralPath $artReport -Raw | ConvertFrom-Json
if ($art.result -ne 'OFFLINE_NORNIR_RESIDENT_ART_BUILT' -or -not $art.ready_for_nornir_wad_clone) {
    throw 'Nornir resident-art gate is not WAD-clone ready.'
}
if ($art.nornir_texpack_sha256 -ne 'f01a3b935e8b54ae5774004b7d77a01312f7304ef31f3237f4e41b1a523fef9d') {
    throw 'Nornir resident-art texpack SHA changed.'
}
$diffuse = @($art.rows | Where-Object { $_.label -eq 'diffuse' })
$emissive = @($art.rows | Where-Object { $_.label -eq 'emissive' })
if ($diffuse.Count -ne 1 -or $emissive.Count -ne 1) { throw 'Resident-art report must contain exactly one diffuse and one emissive row.' }
if ($diffuse[0].resident_sha256 -ne '4912eca29c970d137f584f75627b2cfe30f3681652bec7762f96ff7e0e86e9e4' -or $diffuse[0].resident_bytes -ne 9228) {
    throw 'Nornir diffuse resident payload contract changed.'
}
if ($emissive[0].resident_sha256 -ne 'ab37213e0c654b5ef7047d57b0b1f07f671ca1980a8528d39b8522995ba0244c' -or $emissive[0].resident_bytes -ne 4620) {
    throw 'Nornir emissive resident payload contract changed.'
}
foreach ($row in @($diffuse[0], $emissive[0])) {
    if (-not (Test-Path -LiteralPath $row.output -PathType Leaf)) { throw "Resident payload missing: $($row.output)" }
    if ((Get-FileHash -LiteralPath $row.output -Algorithm SHA256).Hash.ToLowerInvariant() -ne $row.resident_sha256.ToLowerInvariant()) {
        throw "Resident payload SHA mismatch: $($row.output)"
    }
}

$archive = Join-Path $repo 'archive\field-logs\completionist-v104-nornir-resident-art-offline-success.json'
if (-not (Test-Path -LiteralPath $archive -PathType Leaf)) { throw "Archived Nornir resident-art success proof missing: $archive" }
$archived = Get-Content -LiteralPath $archive -Raw | ConvertFrom-Json
if ($archived.result -ne 'NORNIR_RESIDENT_ART_OFFLINE_GATE_PASSED' -or
    $archived.diffuse.sha256 -ne '4912eca29c970d137f584f75627b2cfe30f3681652bec7762f96ff7e0e86e9e4' -or
    $archived.emissive.sha256 -ne 'ab37213e0c654b5ef7047d57b0b1f07f671ca1980a8528d39b8522995ba0244c') {
    throw 'Archived Nornir resident-art proof does not match the passing local payloads.'
}

& $python.Source -m py_compile $builder
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed for Nornir map/HUD builder.' }

$work = Join-Path $repo 'build\v0.10.4-nornir-map-hud\offline'
$report = Join-Path $work 'nornir-map-hud-offline.json'
Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $work | Out-Null

Write-Host 'Cloning runtime-proven Raven map/HUD resource grammar under Nornir identities...'
& $python.Source $builder --game-root $GameRoot --repo-root $repo --art-report $artReport --output-dir $work --report $report
if ($LASTEXITCODE -ne 0) { throw 'Offline Nornir map/HUD build failed.' }
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) { throw 'Nornir map/HUD report was not produced.' }

$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($proof.result -ne 'OFFLINE_NORNIR_MAP_HUD_BUILT' -or -not $proof.ready_for_next_offline_gate) {
    throw 'Nornir map/HUD report did not pass the next-gate contract.'
}
if (-not $proof.proof.candidate_wad_reparsed -or
    -not $proof.proof.candidate_wad_normalizes_exactly_to_raven_production -or
    -not $proof.proof.candidate_gopool_normalizes_exactly_to_raven_production -or
    -not $proof.proof.all_existing_gopool_rows_preserved -or
    -not $proof.proof.raven_resources_preserved) {
    throw 'Nornir map/HUD structural proof is incomplete.'
}
if ($proof.candidate.gopool.source_rows -ne 257 -or
    $proof.candidate.gopool.candidate_rows -ne 259 -or
    $proof.candidate.gopool.map_index -ne 257 -or
    $proof.candidate.gopool.map_capacity -ne 1 -or
    $proof.candidate.gopool.hud_index -ne 258 -or
    $proof.candidate.gopool.hud_capacity -ne 2) {
    throw 'Nornir map/HUD GOPool result does not match the approved plan.'
}
if (-not $proof.candidate.wad.all_wad_header_names_fit_55_bytes) {
    throw 'Nornir WAD-header alias proof did not pass.'
}
if (-not $proof.candidate.wad.accounting.hud_accounting_grammar_verified -or
    $proof.candidate.wad.accounting.fallback_type_key_accounted_payloads -ne 3 -or
    $proof.candidate.wad.accounting.unaccounted_payload_count -ne 1 -or
    $proof.candidate.wad.accounting.unaccounted_payload_names[0] -ne 'MDL_completionistnornirchesthud') {
    throw 'Nornir WAD accounting did not match the runtime-proven Raven HUD grammar.'
}
if ($proof.safety.game_files_written -or $proof.safety.runtime_install_performed -or
    $proof.safety.save_state_written -or $proof.safety.progression_state_written -or
    $proof.safety.marker_state_written -or $proof.safety.raven_production_files_changed) {
    throw 'Nornir map/HUD safety contract failed.'
}

$candidateWad = Join-Path $work 'r_ui.wad'
$candidateDcb = Join-Path $work 'wad_r_ui.dcb'
foreach ($candidate in @($candidateWad, $candidateDcb)) {
    if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "Candidate missing: $candidate" }
}
if ((Get-FileHash -LiteralPath $candidateWad -Algorithm SHA256).Hash.ToLowerInvariant() -ne $proof.candidate.wad.candidate_sha256.ToLowerInvariant()) {
    throw 'Candidate r_ui.wad SHA does not match its report.'
}
if ((Get-FileHash -LiteralPath $candidateDcb -Algorithm SHA256).Hash.ToLowerInvariant() -ne $proof.candidate.gopool.candidate_sha256.ToLowerInvariant()) {
    throw 'Candidate wad_r_ui.dcb SHA does not match its report.'
}

Write-Host 'Re-verifying Raven production state after the offline Nornir map/HUD build...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verify -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Raven production state changed during offline Nornir map/HUD build.' }

Write-Host 'NORNIR_MAP_HUD_OFFLINE_GATE_PASSED'
Write-Host "r_ui.wad:"
Write-Host "  $($proof.candidate.wad.source_sha256)"
Write-Host '  ->'
Write-Host "  $($proof.candidate.wad.candidate_sha256)"
Write-Host "wad_r_ui.dcb:"
Write-Host "  $($proof.candidate.gopool.source_sha256)"
Write-Host '  ->'
Write-Host "  $($proof.candidate.gopool.candidate_sha256)"
Write-Host "WAD payload delta: $($proof.candidate.wad.accounting.payload_delta)"
Write-Host "WAD accounted delta: $($proof.candidate.wad.accounting.accounted_delta)"
Write-Host 'Raven HUD accounting grammar reused: 3 type-key payloads + 1 unaccounted model'
Write-Host 'GOPool rows: 257 -> 259'
Write-Host 'map: goMapIconCompletionistNornirChest index 257 capacity 1'
Write-Host 'HUD: goCompletionistNornirChestHUD index 258 capacity 2'
Write-Host 'resident Nornir art injected exactly: true'
Write-Host 'WAD texture header aliases fit fixed 55-byte name limit: true'
Write-Host 'candidate WAD reparsed and normalized to Raven production: true'
Write-Host 'candidate GOPool normalized to Raven production: true'
Write-Host 'Raven production files changed: false'
Write-Host 'game files written: false'
Write-Host 'runtime install performed: false'
Write-Host "candidate directory: $work"
Write-Host "report: $report"
Write-Host 'Do not install this candidate manually. The next offline gate adds CompletionistNornirChest plus its dedicated in-world carrier and retargets only the offline Nornir native marker candidate.'
