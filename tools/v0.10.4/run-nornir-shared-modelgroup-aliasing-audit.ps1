param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedBranch = 'codex/v104-raven-production'
$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$auditPy = Join-Path $PSScriptRoot 'audit-nornir-shared-modelgroup-aliasing.py'
$candidate = Join-Path $repo 'build\v0.10.4-nornir-lifecycle\offline\candidate\game-root\exec\wad\pc_le\r_ui.wad'
$outDir = Join-Path $repo 'build\v0.10.4-nornir-runtime-failure-audit'
$report = Join-Path $outDir 'nornir-shared-modelgroup-aliasing.json'
$ravenWad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'

function Assert-GodOfWarClosed {
    if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before the read-only shared model-group audit.' }
    if (Get-Process -Name GodOfWar -ErrorAction SilentlyContinue) { throw 'Close God of War before the read-only shared model-group audit.' }
}

$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not determine current Git branch.' }
if ($branch -ne $expectedBranch) { throw "Expected branch '$expectedBranch', got '$branch'." }

Assert-GodOfWarClosed

foreach ($required in @($verifyRaven, $auditPy, $candidate, $ravenWad)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required audit input missing: $required"
    }
}

Write-Host 'Re-verifying exact Raven production state before the shared model-group audit...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production state must pass before this audit.' }

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Remove-Item -LiteralPath $report -Force -ErrorAction SilentlyContinue

Write-Host ''
Write-Host 'Auditing stock MG_mapicondock_0 / MG_boatdock_0 sharing and reverse Nornir references READ-ONLY...'
& python $auditPy --raven-wad $ravenWad --candidate-wad $candidate --report $report | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Nornir shared model-group aliasing audit failed.' }

$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($proof.result -ne 'NORNIR_SHARED_MODEL_GROUP_ALIASING_AUDIT_READ_ONLY' -or
    $proof.safety.game_files_written -or
    $proof.safety.runtime_install_performed -or
    $proof.safety.save_state_written -or
    $proof.safety.progression_state_written -or
    $proof.safety.marker_state_written) {
    throw 'Shared model-group audit did not preserve its read-only contract.'
}

Write-Host ''
Write-Host 'NORNIR_SHARED_MODEL_GROUP_ALIASING_AUDIT_PASSED_READ_ONLY'
Write-Host "  map MG shared Raven/Nornir ID: $($proof.flags.nornir_map_model_reuses_exact_raven_stock_mg_id)"
Write-Host "  HUD MG shared Raven/Nornir ID: $($proof.flags.nornir_hud_model_reuses_exact_raven_stock_mg_id)"
Write-Host "  Nornir material refs outside Nornir groups: $($proof.flags.nornir_material_referenced_outside_nornir_groups)"
Write-Host "  Nornir diffuse refs outside Nornir groups: $($proof.flags.nornir_diffuse_referenced_outside_nornir_groups)"
Write-Host "  Nornir emissive refs outside Nornir groups: $($proof.flags.nornir_emissive_referenced_outside_nornir_groups)"
Write-Host "  shared stock model-group isolation gap: $($proof.interpretation.shared_stock_model_group_identity_is_a_real_isolation_gap)"
Write-Host '  root cause proven: false'
Write-Host '  game files written: false'
Write-Host '  runtime install performed: false'
Write-Host "  report: $report"
Write-Host ''
Write-Host 'Do not install another Nornir candidate. If the Nornir material/textures do not leak into stock/Raven groups but the shared MG IDs are confirmed, the next gate is an OFFLINE Nornir-only MG clone/isolation candidate.'
