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
if ($gow) { throw 'God of War must be closed for this offline candidate #2 assembly gate.' }

$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$auditRunner = Join-Path $PSScriptRoot 'run-nornir-mg-isolated-candidate-audit.ps1'
$builder = Join-Path $PSScriptRoot 'build-nornir-runtime-candidate2-offline.py'
$lifecycleRoot = Join-Path $repo 'build\v0.10.4-nornir-lifecycle\offline\candidate\game-root'
$isolatedWad = Join-Path $repo 'build\v0.10.4-nornir-mg-isolation\offline\r_ui.wad'
$archivedAudit = Join-Path $repo 'archive\field-logs\completionist-v104-nornir-mg-isolated-candidate-audit.json'
$outRoot = Join-Path $repo 'build\v0.10.4-nornir-runtime-candidate2\offline'
$candidateRoot = Join-Path $outRoot 'candidate\game-root'
$report = Join-Path $outRoot 'nornir-runtime-candidate2.json'

Write-Host 'Re-verifying frozen Raven production before runtime candidate #2 assembly...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven verifier failed before candidate #2 assembly.' }

Write-Host ''
Write-Host 'Re-running the post-isolation reverse-reference audit before assembly...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $auditRunner -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Isolated Nornir MG candidate audit did not pass immediately before candidate #2 assembly.' }

foreach ($required in @($builder, $lifecycleRoot, $isolatedWad, $archivedAudit)) {
    if (-not (Test-Path -LiteralPath $required)) { throw "Missing candidate #2 prerequisite: $required" }
}

if (Test-Path -LiteralPath $outRoot) {
    Remove-Item -LiteralPath $outRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $outRoot | Out-Null

Write-Host ''
Write-Host 'Assembling runtime candidate #2 OFFLINE from the lifecycle candidate plus isolated r_ui.wad...'
& python $builder `
    --lifecycle-root $lifecycleRoot `
    --isolated-wad $isolatedWad `
    --audit-report $archivedAudit `
    --output-root $candidateRoot `
    --report $report | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Runtime candidate #2 offline assembler failed.' }

$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($proof.result -ne 'OFFLINE_NORNIR_RUNTIME_CANDIDATE2_ASSEMBLED') { throw "Unexpected candidate #2 report result: $($proof.result)" }
if (-not $proof.proofs.exactly_ten_files_present) { throw 'Candidate #2 does not contain exactly ten files.' }
if (-not $proof.proofs.only_r_ui_wad_differs_from_lifecycle_candidate) { throw 'Candidate #2 changes more than r_ui.wad.' }
if (-not $proof.proofs.r_ui_wad_is_exact_isolated_mg_candidate) { throw 'Candidate #2 r_ui.wad is not the isolated MG WAD.' }
if (-not $proof.proofs.all_other_nine_files_byte_identical_to_lifecycle_candidate) { throw 'Candidate #2 changed one or more non-WAD lifecycle files.' }
if (-not $proof.proofs.isolated_mg_audit_cleared_runtime_candidate_2_assembly) { throw 'Candidate #2 was assembled without a passing isolation audit.' }
if (-not $proof.proofs.candidate2_ready_for_transactional_installer_gate) { throw 'Candidate #2 did not clear the transactional-installer gate.' }
if ($proof.safety.game_files_written -or $proof.safety.runtime_install_performed -or
    $proof.safety.save_state_written -or $proof.safety.progression_state_written -or
    $proof.safety.marker_state_written) {
    throw 'Candidate #2 offline safety contract was violated.'
}

Write-Host ''
Write-Host 'Re-verifying frozen Raven production after OFFLINE candidate #2 assembly...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven verifier failed after candidate #2 assembly.' }

Write-Host ''
Write-Host 'NORNIR_RUNTIME_CANDIDATE2_OFFLINE_GATE_PASSED'
Write-Host '  ten-file candidate complete: true'
Write-Host '  only r_ui.wad differs from the previously-proven lifecycle candidate: true'
Write-Host '  r_ui.wad = isolated MG candidate: true'
Write-Host '  other nine files byte-identical to lifecycle candidate: true'
Write-Host '  isolated MG reverse-reference audit passed immediately before assembly: true'
Write-Host '  game files written: false'
Write-Host '  saves/progression/marker state written: false'
Write-Host '  runtime install performed: false'
Write-Host ("  candidate root: {0}" -f $candidateRoot)
Write-Host ("  report: {0}" -f $report)
Write-Host ''
Write-Host 'Do not copy candidate #2 into God of War manually. If this gate passes, the next step is a fresh transactional installer/rollback path for runtime candidate #2.'
