param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$branch = (& git -C $repo rev-parse --abbrev-ref HEAD).Trim()
if ($branch -ne 'codex/v104-raven-production') {
    throw "Wrong branch: $branch. Expected codex/v104-raven-production"
}

$gow = Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match 'GodOfWar|GoW' }
if ($gow) { throw 'God of War must be closed for this offline isolation gate.' }

$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$builder = Join-Path $PSScriptRoot 'build-nornir-mg-isolation-offline-v3.py'
$accountingTests = Join-Path $PSScriptRoot 'test_nornir_mg_accounting.py'
$failedCandidate = Join-Path $repo 'build\v0.10.4-nornir-lifecycle\offline\candidate\game-root\exec\wad\pc_le\r_ui.wad'
$ravenWad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
$outRoot = Join-Path $repo 'build\v0.10.4-nornir-mg-isolation\offline'
$outWad = Join-Path $outRoot 'r_ui.wad'
$report = Join-Path $outRoot 'nornir-mg-isolation.json'

Write-Host 'Re-verifying exact Raven production state before building the Nornir-only model-group isolation candidate...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verifier failed before Nornir MG isolation build.' }

if (-not (Test-Path -LiteralPath $failedCandidate -PathType Leaf)) {
    throw "Failed Nornir lifecycle candidate WAD is missing: $failedCandidate"
}

$failedSha = (Get-FileHash -LiteralPath $failedCandidate -Algorithm SHA256).Hash.ToLowerInvariant()
if ($failedSha -ne '340e0ceccd8d399e39612355b4b05e387c48809a654e765530346b029ba2a16c') {
    throw "Failed candidate WAD SHA changed: $failedSha"
}

if (Test-Path -LiteralPath $outRoot) {
    Remove-Item -LiteralPath $outRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $outRoot | Out-Null

Write-Host 'Running focused frozen-Raven MG accounting grammar tests...'
& python $accountingTests
if ($LASTEXITCODE -ne 0) { throw 'Focused Nornir MG accounting tests failed.' }

Write-Host 'Cloning standalone MG_mapicondock_0 / MG_boatdock_0 under dedicated Nornir identities OFFLINE...'
& python $builder `
    --failed-candidate-wad $failedCandidate `
    --raven-wad $ravenWad `
    --output $outWad `
    --report $report | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Offline Nornir model-group isolation builder failed.' }

$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($proof.result -ne 'OFFLINE_NORNIR_MG_ISOLATION_BUILT') { throw "Unexpected isolation report result: $($proof.result)" }
if (-not $proof.proofs.stock_mg_payloads_are_standalone_records) { throw 'Stock MG donor payloads were not proven standalone.' }
if (-not $proof.proofs.standalone_stock_mg_records_match_raven_baseline_byte_exactly) { throw 'Standalone stock MG donors differ from Raven baseline.' }
if (-not $proof.proofs.standalone_resource_span_logic_used) { throw 'Standalone-safe resource-span logic was not used.' }
if (-not $proof.proofs.mg_donor_accounting_grammar_proven_from_frozen_raven_wad) { throw 'Frozen Raven MG accounting grammar was not proven.' }
if (-not $proof.proofs.both_mg_clone_payloads_strictly_accounted) { throw 'Both MG clone payloads were not strictly accounted.' }
if (-not $proof.proofs.no_mg_clone_payload_intentionally_unaccounted) { throw 'An MG clone payload was left unaccounted.' }
if (-not $proof.proofs.shared_stock_model_group_isolation_gap_closed) { throw 'Shared stock model-group gap is not closed.' }
if (-not $proof.proofs.nornir_map_model_uses_dedicated_mg_only) { throw 'Nornir map model is not isolated to its dedicated MG.' }
if (-not $proof.proofs.nornir_hud_model_uses_dedicated_mg_only) { throw 'Nornir HUD model is not isolated to its dedicated MG.' }
if (-not $proof.proofs.raven_map_model_still_uses_stock_mg) { throw 'Raven map model changed during Nornir MG isolation.' }
if (-not $proof.proofs.raven_hud_model_still_uses_stock_mg) { throw 'Raven HUD model changed during Nornir MG isolation.' }
if (-not $proof.proofs.isolated_candidate_normalizes_to_failed_candidate_byte_exactly) { throw 'Isolated WAD does not normalize exactly to the failed candidate.' }
if (-not $proof.proofs.candidate_reparse_roundtrip_exact) { throw 'Isolated WAD did not round-trip exactly.' }
if ($proof.safety.game_files_written -or $proof.safety.runtime_install_performed) { throw 'Offline safety contract was violated.' }
if (-not $proof.accounting.mg_accounting_grammar_verified -or
    $proof.accounting.payload_delta -ne 2 -or
    $proof.accounting.accounted_delta -ne 2 -or
    $proof.accounting.direct_index_accounted_payloads -ne 1 -or
    $proof.accounting.fallback_type_key_accounted_payloads -ne 1 -or
    $proof.accounting.unaccounted_payload_count -ne 0 -or
    $proof.accounting.type_increments.'0x1000C' -ne 1 -or
    $proof.accounting.type_increments.'0x2000C' -ne 1) {
    throw 'Nornir MG accounting does not match exact frozen Raven grammar.'
}

$ravenMap = $proof.mg_donor_accounting_facts.frozen_raven.map
$ravenHud = $proof.mg_donor_accounting_facts.frozen_raven.hud
if ($ravenMap.record_index -ne 32419 -or $ravenMap.payload_index -ne 13912 -or
    $ravenMap.record_id -ne '44b11676af9c4e0ff860108fd46b0b32' -or
    $ravenMap.kind -ne 1 -or $ravenMap.flags -ne '0x98' -or
    $ravenMap.payload_byte_length -ne 1108 -or $ravenMap.first_dword -ne '0x1000C' -or
    -not $ravenMap.payload_index_in_ordinary_type_range -or
    -not $ravenMap.first_dword_matches_existing_type_key -or
    $ravenMap.accounting_mode -ne 'ordinary_payload_index' -or
    $ravenMap.accounting_type_key -ne '0x2000C' -or
    $ravenMap.intentionally_physically_present_but_unaccounted) {
    throw 'Frozen Raven MG_mapicondock_0 accounting facts changed.'
}
if ($ravenHud.record_index -ne 49144 -or $ravenHud.payload_index -ne 18487 -or
    $ravenHud.record_id -ne 'c3f6b4c5a8270df607ea3e6e7f891292' -or
    $ravenHud.kind -ne 1 -or $ravenHud.flags -ne '0x98' -or
    $ravenHud.payload_byte_length -ne 388 -or $ravenHud.first_dword -ne '0x1000C' -or
    $ravenHud.payload_index_in_ordinary_type_range -or
    -not $ravenHud.first_dword_matches_existing_type_key -or
    $ravenHud.accounting_mode -ne 'first_dword_type_key' -or
    $ravenHud.accounting_type_key -ne '0x1000C' -or
    $ravenHud.intentionally_physically_present_but_unaccounted) {
    throw 'Frozen Raven MG_boatdock_0 accounting facts changed.'
}
if (-not $proof.comparable_raven_accounting.map_resources_use_ordinary_payload_index_accounting -or
    -not $proof.comparable_raven_accounting.hud_prototype_scp_root_use_first_dword_type_key_accounting -or
    -not $proof.comparable_raven_accounting.hud_model_is_physically_present_but_unaccounted -or
    -not $proof.comparable_raven_accounting.mg_hud_matches_accounted_type_key_grammar_not_unaccounted_model_grammar) {
    throw 'Comparable frozen Raven accounting grammar changed.'
}

Write-Host ''
Write-Host 'Re-verifying exact Raven production state after the OFFLINE Nornir MG isolation build...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verifier failed after Nornir MG isolation build.' }

Write-Host ''
Write-Host 'NORNIR_MG_ISOLATION_OFFLINE_GATE_PASSED'
Write-Host ("  isolated WAD SHA256: {0}" -f $proof.candidate_sha256)
Write-Host ("  map donor shape: standalone payload, id={0}" -f $proof.standalone_stock_mg_donors.map.id)
Write-Host ("  HUD donor shape: standalone payload, id={0}" -f $proof.standalone_stock_mg_donors.hud.id)
Write-Host '  MG accounting: map direct 0x2000C + HUD first-dword fallback 0x1000C'
Write-Host '  MG accounting delta: +2 physical payloads / +2 accounted payloads / 0 unaccounted'
Write-Host ("  map MG: {0} / {1}" -f $proof.dedicated_model_groups.map.new_name, $proof.dedicated_model_groups.map.new_id)
Write-Host ("  HUD MG: {0} / {1}" -f $proof.dedicated_model_groups.hud.new_name, $proof.dedicated_model_groups.hud.new_id)
Write-Host '  stock MG donors match Raven baseline byte-exactly: true'
Write-Host '  Nornir map/HUD models use dedicated MGs only: true'
Write-Host '  Raven map/HUD models still use stock MGs: true'
Write-Host '  candidate reparsed/round-tripped exactly: true'
Write-Host '  isolated candidate normalizes to failed candidate byte-exactly: true'
Write-Host '  failed candidate previously normalized to frozen Raven WAD: true'
Write-Host '  shared stock model-group isolation gap closed: true'
Write-Host '  game files written: false'
Write-Host '  saves/progression/marker state written: false'
Write-Host '  runtime install performed: false'
Write-Host ("  report: {0}" -f $report)
Write-Host ''
Write-Host 'Do not install this WAD manually. If this gate passes, audit the isolated candidate before constructing a second transactional runtime candidate.'
