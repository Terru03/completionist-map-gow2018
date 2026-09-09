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
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before the read-only Nornir resource isolation audit.' }
if (Get-Process -Name GodOfWar -ErrorAction SilentlyContinue) { throw 'Close God of War before the read-only Nornir resource isolation audit.' }

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) { throw 'Python 3 is required.' }

$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$audit = Join-Path $PSScriptRoot 'audit-nornir-map-resource-isolation.py'
$candidate = Join-Path $repo 'build\v0.10.4-nornir-lifecycle\offline\candidate\game-root\exec\wad\pc_le\r_ui.wad'
$liveRaven = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'
$state = Join-Path $repo 'build\v0.10.4-nornir-runtime-failure-audit'
$report = Join-Path $state 'nornir-map-resource-isolation.json'

foreach ($required in @($verifyRaven, $audit, $candidate, $liveRaven)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required audit input: $required" }
}

Write-Host 'Re-verifying exact Raven production state before reading the failed Nornir candidate...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) {
    throw 'Frozen Raven production state is not restored. Roll back the failed Nornir runtime transaction before auditing.'
}

& $python.Source -m py_compile $audit
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed for Nornir resource isolation audit.' }

Remove-Item -LiteralPath $state -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $state | Out-Null

Write-Host ''
Write-Host 'Auditing stock/Raven/Nornir map-resource identities and dependency links READ-ONLY...'
& $python.Source $audit `
    --raven-wad $liveRaven `
    --candidate-wad $candidate `
    --report $report
if ($LASTEXITCODE -ne 0) { throw 'Nornir map resource isolation audit failed.' }

$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($proof.result -ne 'NORNIR_MAP_RESOURCE_ISOLATION_AUDIT_READ_ONLY' -or
    $proof.safety.game_files_written -or
    $proof.safety.runtime_install_performed -or
    $proof.safety.save_state_written -or
    $proof.safety.progression_state_written -or
    $proof.safety.marker_state_written) {
    throw 'Nornir map resource isolation audit violated its read-only contract.'
}

Write-Host ''
Write-Host 'NORNIR_MAP_RESOURCE_ISOLATION_AUDIT_PASSED_READ_ONLY'
Write-Host "  map model payload byte-identical to Raven donor: $($proof.pairs.map_model.payload_byte_identical)"
Write-Host "  HUD model payload byte-identical to Raven donor: $($proof.pairs.hud_model.payload_byte_identical)"
Write-Host "  material payload byte-identical to Raven donor: $($proof.pairs.material.payload_byte_identical)"
Write-Host "  map prototype Raven-ID remnants: $(@($proof.pairs.map_proto.raven_record_id_occurrences_in_nornir_payload).Count)"
Write-Host "  map root Raven-ID remnants: $(@($proof.pairs.map_root.raven_record_id_occurrences_in_nornir_payload).Count)"
Write-Host '  game files written: false'
Write-Host '  runtime install performed: false'
Write-Host "  report: $report"
Write-Host ''
Write-Host 'Do not install another Nornir candidate yet. Review this audit first.'
