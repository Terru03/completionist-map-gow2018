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
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before the read-only Nornir GOPool relocation audit.' }
if (Get-Process -Name GodOfWar -ErrorAction SilentlyContinue) { throw 'Close God of War before the read-only Nornir GOPool relocation audit.' }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }

$python = Get-Command python.exe -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($null -eq $python) { throw 'Python 3 is required.' }

$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$audit = Join-Path $PSScriptRoot 'audit-nornir-gopool-relocations.py'
$candidateDcb = Join-Path $repo 'build\v0.10.4-nornir-lifecycle\offline\candidate\game-root\exec\dc\pc_le\wad_r_ui.dcb'
$liveDcb = Join-Path $GameRoot 'exec\dc\pc_le\wad_r_ui.dcb'
$state = Join-Path $repo 'build\v0.10.4-nornir-runtime-failure-audit'
$report = Join-Path $state 'nornir-gopool-relocations.json'

foreach ($required in @($verifyRaven, $audit, $candidateDcb, $liveDcb)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required audit input: $required" }
}

& $python.Source -m py_compile $audit
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed for Nornir GOPool relocation audit.' }

Write-Host 'Re-verifying exact Raven production state before the DCB relocation audit...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verification failed.' }

New-Item -ItemType Directory -Force -Path $state | Out-Null
Remove-Item -LiteralPath $report -Force -ErrorAction SilentlyContinue

Write-Host ''
Write-Host 'Auditing the failed +2-row GOPool candidate against DCB relocation semantics READ-ONLY...'
& $python.Source $audit --raven-dcb $liveDcb --candidate-dcb $candidateDcb --report $report
if ($LASTEXITCODE -ne 0) { throw 'Nornir GOPool relocation audit failed.' }
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) { throw 'Nornir GOPool relocation audit report was not produced.' }

$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($proof.result -ne 'NORNIR_GOPOOL_RELOCATION_AUDIT_READ_ONLY' -or
    $proof.safety.game_files_written -or
    $proof.safety.runtime_install_performed -or
    $proof.safety.save_state_written -or
    $proof.safety.progression_state_written -or
    $proof.safety.marker_state_written) {
    throw 'Nornir GOPool relocation audit did not satisfy the read-only contract.'
}

Write-Host ''
Write-Host 'NORNIR_GOPOOL_RELOCATION_AUDIT_PASSED_READ_ONLY'
Write-Host ("  chunk12 insertion requires relocation transform: {0}" -f $proof.diagnosis.chunk12_insertion_requires_relocation_transform)
Write-Host ("  failed candidate left chunk15 stale: {0}" -f $proof.diagnosis.failed_candidate_left_chunk15_stale)
Write-Host ("  failed candidate has runtime-unsafe relocations: {0}" -f $proof.diagnosis.failed_candidate_has_runtime_unsafe_relocations)
Write-Host ("  relocation fields at/after insertion: {0}" -f $proof.relocations.relocation_fields_at_or_after_insertion)
Write-Host ("  cross-insertion pointers: {0}" -f $proof.relocations.cross_insertion_relative_pointers)
Write-Host ("  missing expected relocation fields: {0}" -f @($proof.relocations.missing_expected_relocation_fields).Count)
Write-Host ("  stale/unexpected relocation fields: {0}" -f @($proof.relocations.unexpected_candidate_relocation_fields).Count)
Write-Host '  game files written: false'
Write-Host '  runtime install performed: false'
Write-Host ("  report: {0}" -f $report)
Write-Host ''
Write-Host 'Do not install another Nornir candidate. If relocation corruption is proven, fix and reparse WAD_R_UI DCB offline before revisiting WAD resource aliasing.'
