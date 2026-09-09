param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedBranch = 'codex/v104-raven-production'
$verifyRaven = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
$audit = Join-Path $PSScriptRoot 'audit-nornir-material-reference-owners.py'
$candidate = Join-Path $repo 'build\v0.10.4-nornir-lifecycle\offline\candidate\game-root\exec\wad\pc_le\r_ui.wad'
$outDir = Join-Path $repo 'build\v0.10.4-nornir-runtime-failure-audit'
$report = Join-Path $outDir 'nornir-material-reference-owners.json'
$ravenWad = Join-Path $GameRoot 'exec\wad\pc_le\r_ui.wad'

$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Could not determine current Git branch.' }
if ($branch -ne $expectedBranch) { throw "Expected branch '$expectedBranch', got '$branch'." }
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) { throw 'Close God of War before the read-only material-reference audit.' }
if (Get-Process -Name GodOfWar -ErrorAction SilentlyContinue) { throw 'Close God of War before the read-only material-reference audit.' }

foreach ($required in @($verifyRaven, $audit, $candidate, $ravenWad)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}

Write-Host 'Re-verifying exact Raven production state before classifying Nornir material references...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verifyRaven -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven production verification failed.' }

New-Item -ItemType Directory -Force -Path $outDir | Out-Null
Remove-Item -LiteralPath $report -Force -ErrorAction SilentlyContinue

Write-Host ''
Write-Host 'Classifying every Nornir material reference by exact containing resource owner READ-ONLY...'
& python $audit --raven-wad $ravenWad --candidate-wad $candidate --report $report | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Nornir material reference owner audit failed.' }

$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ($proof.result -ne 'NORNIR_MATERIAL_REFERENCE_OWNERS_AUDIT_READ_ONLY' -or
    $proof.safety.game_files_written -or
    $proof.safety.runtime_install_performed -or
    $proof.safety.save_state_written -or
    $proof.safety.progression_state_written -or
    $proof.safety.marker_state_written) {
    throw 'Material reference audit report failed its read-only contract.'
}

Write-Host ''
Write-Host 'NORNIR_MATERIAL_REFERENCE_OWNER_AUDIT_PASSED_READ_ONLY'
Write-Host "  total references: $(@($proof.references).Count)"
Write-Host "  dangerous stock/Raven leaks: $($proof.dangerous_stock_or_raven_leak_count)"
Write-Host "  unexplained other-scope refs: $($proof.unexplained_other_scope_count)"
Write-Host "  previous outside-scope flag benign/understood: $($proof.safe_to_interpret_previous_outside_scope_flag)"
Write-Host '  game files written: false'
Write-Host '  runtime install performed: false'
Write-Host "  report: $report"
Write-Host ''
Write-Host 'Do not install another Nornir candidate. Review the exact material-reference owners before deciding whether to clone the shared model groups.'
