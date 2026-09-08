param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin',
    [switch]$NoPublish
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War before the R_Perm indirect-population trace.'
}

$game = [IO.Path]::GetFullPath($GameRoot)
$scanner = Join-Path $PSScriptRoot 'inspect-r-perm-connect-indirect-population.py'
$outRel = 'archive/field-logs/completionist-v104-r-perm-connect-indirect-population.json'
$out = Join-Path $repo ($outRel -replace '/', '\')

if (-not (Test-Path -LiteralPath $scanner -PathType Leaf)) { throw "Missing tracer: $scanner" }
if (-not (Test-Path -LiteralPath $game -PathType Container)) { throw "Missing game root: $game" }
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3.9+ is required.' }

$preStaged = @(& git -C $repo diff --cached --name-only)
if ($preStaged.Count -gt 0 -and -not [string]::IsNullOrWhiteSpace(($preStaged -join ''))) {
    throw "Git index already has staged changes. Commit/unstage them first.`n$($preStaged -join "`n")"
}

Write-Host 'Syntax-checking R_Perm indirect-population tracer...'
& $python.Source -m py_compile $scanner
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed.' }

Write-Host 'Classifying R_Perm source-slot writes and indirect callbacks read-only...'
& $python.Source $scanner --game-root $game --output $out
if ($LASTEXITCODE -ne 0) { throw 'R_Perm indirect-population trace failed.' }
if (-not (Test-Path -LiteralPath $out -PathType Leaf)) { throw "Report was not produced: $out" }

$r = Get-Content -LiteralPath $out -Raw | ConvertFrom-Json
if ([string]$r.result -ne 'READ_ONLY_R_PERM_INDIRECT_POPULATION_TRACE') {
    throw "Unexpected result: $($r.result)"
}
if ($r.game_files_written -ne $false -or $r.save_progression_marker_state_written -ne $false) {
    throw 'Read-only safety flags failed.'
}
if ([string]$r.rperm_call_proof.rcx_string -ne 'R_Perm' -or $r.rperm_call_proof.edx_zeroed -ne $true) {
    throw 'R_Perm call argument proof failed.'
}
if ([string]$r.semantic_correction.classification -ne 'proven_zero_clear') {
    throw 'Could not prove the previously reached writer is a zero-clear.'
}

Write-Host ''
Write-Host 'R_Perm indirect-population trace complete.'
Write-Host ("- source-slot writes: {0}; proven clears: {1}; unknown/potential: {2}" -f `
    [int]$r.source_slot.write_instruction_count, `
    [int]$r.source_slot.proven_zero_clear_count, `
    [int]$r.source_slot.potential_population_or_unknown_count)
Write-Host '- 0x421040 -> 0x41F640 is a proven ZERO/CLEAR path, not population'
Write-Host ("- indirect-call candidates: {0}" -f [int]$r.heuristic_indirect_call_candidate_count)
Write-Host ("- conclusion: {0}" -f [string]$r.conclusion)
Write-Host ("- report: {0}" -f $out)
Write-Host '- game files written: false'

if ($NoPublish) {
    Write-Host 'Report publishing skipped (-NoPublish).'
    return
}

& git -C $repo add -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
& git -C $repo diff --cached --check -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed.' }
& git -C $repo diff --cached --quiet -- $outRel
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Report unchanged; nothing new to commit.'
    return
}

& git -C $repo commit -m 'Archive R_Perm indirect population trace' -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git commit failed.' }
& git -C $repo push $Remote $branch
if ($LASTEXITCODE -ne 0) { throw 'git push failed.' }
Write-Host "Report committed and pushed to $Remote/$branch."
