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
if ($gow) { throw 'God of War must be closed for this read-only audit.' }

$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$audit = Join-Path $PSScriptRoot 'audit-nornir-mg-isolated-candidate.py'
$ravenWad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
$failedWad = Join-Path $repo 'build\v0.10.4-nornir-lifecycle\offline\candidate\game-root\exec\wad\pc_le\r_ui.wad'
$isolatedWad = Join-Path $repo 'build\v0.10.4-nornir-mg-isolation\offline\r_ui.wad'
$outRoot = Join-Path $repo 'build\v0.10.4-nornir-mg-isolation-audit'
$report = Join-Path $outRoot 'nornir-mg-isolated-candidate-audit.json'

Write-Host 'Re-verifying exact Raven production state before auditing the isolated Nornir MG candidate...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verifier failed before isolated Nornir MG audit.' }

foreach ($item in @(
    @{ Path = $failedWad; Sha = '340e0ceccd8d399e39612355b4b05e387c48809a654e765530346b029ba2a16c'; Label = 'failed candidate WAD' },
    @{ Path = $isolatedWad; Sha = '96772dd9e36e1d3050ad936dbb9d8d8dfadb39ed2d7b4f74e400c2844877acef'; Label = 'isolated candidate WAD' }
)) {
    if (-not (Test-Path -LiteralPath $item.Path -PathType Leaf)) {
        throw "$($item.Label) missing: $($item.Path)"
    }
    $actual = (Get-FileHash -LiteralPath $item.Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $item.Sha) {
        throw "$($item.Label) SHA changed: $actual"
    }
}

if (Test-Path -LiteralPath $outRoot) {
    Remove-Item -LiteralPath $outRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $outRoot | Out-Null

Write-Host 'Auditing dedicated Nornir MG reverse references and stock/Raven isolation READ-ONLY...'
& python $audit `
    --raven-wad $ravenWad `
    --failed-wad $failedWad `
    --isolated-wad $isolatedWad `
    --report $report | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Post-isolation Nornir MG audit failed.' }

$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($proof.result -ne 'NORNIR_MG_ISOLATED_CANDIDATE_AUDIT_READ_ONLY') { throw "Unexpected audit result: $($proof.result)" }
if (-not $proof.proofs.isolated_candidate_reparse_roundtrip_exact) { throw 'Isolated WAD did not reparse/round-trip exactly.' }
if (-not $proof.proofs.original_stock_mg_payloads_preserved) { throw 'Original stock MG payloads changed.' }
if (-not $proof.proofs.dedicated_mg_payloads_match_stock_donors) { throw 'Dedicated Nornir MG payloads do not match their donors.' }
if (-not $proof.proofs.nornir_models_use_dedicated_mg_only) { throw 'Nornir models are not isolated to dedicated MGs.' }
if (-not $proof.proofs.raven_models_use_stock_mg_only) { throw 'Raven models no longer use only the original stock MGs.' }
if (-not $proof.proofs.dedicated_mg_reverse_refs_exactly_intended_nornir_models) { throw 'Dedicated Nornir MG reverse-reference boundary failed.' }
if (-not $proof.proofs.raven_model_groups_unchanged) { throw 'Raven model groups changed.' }
if (-not $proof.proofs.nornir_material_refs_do_not_leak) { throw 'Nornir material reference leak detected.' }
if (-not $proof.proofs.nornir_texture_refs_do_not_leak) { throw 'Nornir texture reference leak detected.' }
if (-not $proof.proofs.shared_stock_model_group_isolation_gap_closed) { throw 'Shared stock model-group isolation gap remains open.' }
if (-not $proof.proofs.safe_to_assemble_runtime_candidate_2) { throw 'Audit did not clear runtime candidate #2 assembly.' }
if ($proof.safety.game_files_written -or $proof.safety.runtime_install_performed -or
    $proof.safety.save_state_written -or $proof.safety.progression_state_written -or
    $proof.safety.marker_state_written) {
    throw 'Read-only audit safety contract was violated.'
}

Write-Host ''
Write-Host 'Re-verifying exact Raven production state after the READ-ONLY isolated MG audit...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verifier failed after isolated Nornir MG audit.' }

Write-Host ''
Write-Host 'NORNIR_MG_ISOLATED_CANDIDATE_AUDIT_PASSED_READ_ONLY'
Write-Host ("  isolated WAD SHA256: {0}" -f $proof.sha256.isolated_candidate)
Write-Host '  Nornir map -> dedicated Nornir map MG only: true'
Write-Host '  Nornir HUD -> dedicated Nornir HUD MG only: true'
Write-Host '  Raven map/HUD -> original stock MGs only: true'
Write-Host '  dedicated MG reverse refs outside intended Nornir models: 0'
Write-Host '  Nornir material/texture leaks into stock/Raven resources: 0'
Write-Host '  stock MG payloads changed: false'
Write-Host '  Raven model groups changed: false'
Write-Host '  shared stock model-group isolation gap closed: true'
Write-Host '  safe to assemble runtime candidate #2: true'
Write-Host '  game files written: false'
Write-Host '  saves/progression/marker state written: false'
Write-Host '  runtime install performed: false'
Write-Host ("  report: {0}" -f $report)
Write-Host ''
Write-Host 'Do not install anything yet. If this audit passes, the next step is to assemble runtime candidate #2 transactionally from the already-proven lifecycle candidate plus this isolated r_ui.wad.'
