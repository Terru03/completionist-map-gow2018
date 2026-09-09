param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$Remote = 'origin'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = (& git -C $repo branch --show-current).Trim()
if ($branch -ne 'codex/v104-raven-hud-research') {
    throw "Expected codex/v104-raven-hud-research, got '$branch'."
}
if (Get-Process -Name GoW -ErrorAction SilentlyContinue) {
    throw 'Close God of War completely before running the native Raven no-render forensic gate.'
}
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }

$compare = Join-Path $PSScriptRoot 'compare-native-raven-no-render.py'
$trace = Join-Path $PSScriptRoot 'trace-native-raven-no-render.py'
$ab = Join-Path $PSScriptRoot 'native-raven-data-ab.py'
$tests = Join-Path $PSScriptRoot 'test_native_raven_no_render.py'
$reportRel = 'archive/field-logs/completionist-v104-native-raven-no-render-comparison.json'
$report = Join-Path $repo ($reportRel -replace '/', '\')
$traceRel = 'archive/field-logs/completionist-v104-native-raven-no-render-native-gates.json'
$traceReport = Join-Path $repo ($traceRel -replace '/', '\')

foreach ($required in @($compare, $trace, $ab, $tests)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required forensic tool missing: $required"
    }
}

Write-Host 'Syntax-checking native Raven no-render tools...'
& $python.Source -m py_compile $compare $trace $ab $tests
if ($LASTEXITCODE -ne 0) { throw 'Python syntax check failed.' }

Write-Host 'Running disposable forensic/A-B unit tests...'
& $python.Source $tests
if ($LASTEXITCODE -ne 0) { throw 'Native Raven no-render unit tests failed.' }

Write-Host ''
Write-Host 'Running read-only known-good vs current semantic comparison...'
& $python.Source $compare --game-root $GameRoot --output $report
if ($LASTEXITCODE -ne 0) { throw 'Native Raven semantic comparison failed.' }
if (-not (Test-Path -LiteralPath $report -PathType Leaf)) { throw 'Comparison report was not created.' }

$proof = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
if ([string]$proof.result -notin @('ROOT_CAUSE_NARROWED_NOT_PROVEN','ROOT_CAUSE_PROVEN')) {
    throw "Comparison did not narrow the regression sufficiently. Result: $($proof.result)"
}
if ($proof.safety.game_launched -ne $false -or
    $proof.safety.game_files_written -ne $false -or
    $proof.safety.saves_or_progression_accessed -ne $false -or
    $proof.safety.inventory_unchanged_during_analysis -ne $true) {
    throw 'Comparison safety/inventory invariants did not pass.'
}

$native = $proof.native_comparison
$candidate = $native.live.candidate
$missingCoordinate = ($null -eq $candidate.coordinate)
$missingEdge = (@($candidate.edges).Count -eq 0)
if (-not $missingCoordinate -or -not $missingEdge) {
    throw 'Expected current Raven coordinate+graph regression was not proven by semantic parse.'
}
if ($proof.ab_control.eligible -ne $true) {
    throw 'Comparison did not qualify the two-file native-data A/B.'
}

Write-Host ''
Write-Host 'Validating the two-file A/B installer without writing game files...'
& $python.Source $ab --mode check --game-root $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Native Raven two-file A/B check failed.' }

$objdump = Get-Command objdump -ErrorAction SilentlyContinue
$traceCreated = $false
if ($null -ne $objdump) {
    Write-Host ''
    Write-Host 'Running optional read-only native gate trace with objdump...'
    & $python.Source $trace --game-root $GameRoot --objdump $objdump.Source --output $traceReport
    if ($LASTEXITCODE -ne 0) { throw 'Native Raven executable gate trace failed.' }
    $traceCreated = Test-Path -LiteralPath $traceReport -PathType Leaf
} else {
    Write-Host ''
    Write-Host 'objdump not found; skipping optional executable disassembly trace.'
}

Write-Host ''
Write-Host 'NATIVE_RAVEN_NO_RENDER_FORENSIC_GATE_PASSED'
Write-Host ("  result:                 {0}" -f [string]$proof.result)
Write-Host ("  current Raven coord:    {0}" -f ($(if ($missingCoordinate) { 'MISSING' } else { 'present' })))
Write-Host ("  current Raven graph:    {0}" -f ($(if ($missingEdge) { 'MISSING' } else { 'present' })))
Write-Host ("  A/B eligible:           {0}" -f [string]$proof.ab_control.eligible)
Write-Host '  A/B writes if installed: mapcoords.dcb + compassgraph.dcb ONLY'
Write-Host '  game files written now: false'
Write-Host ("  comparison report:      {0}" -f $report)
if ($traceCreated) { Write-Host ("  native gate report:     {0}" -f $traceReport) }
Write-Host '  next: inspect archived reports, then explicitly authorize reversible A/B install'

Push-Location $repo
try {
    $stage = @($reportRel)
    if ($traceCreated) { $stage += $traceRel }
    & git add -- $stage
    if ($LASTEXITCODE -ne 0) { throw 'git add failed for forensic report(s).' }
    & git diff --cached --check -- $stage
    if ($LASTEXITCODE -ne 0) { throw 'git diff --cached --check failed for forensic report(s).' }
    & git diff --cached --quiet -- $stage
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Forensic reports unchanged; nothing new to commit.'
    } else {
        & git commit -m 'Archive native Raven no-render forensic gate' -- $stage
        if ($LASTEXITCODE -ne 0) { throw 'git commit failed for forensic report(s).' }
        & git push $Remote $branch
        if ($LASTEXITCODE -ne 0) { throw 'git push failed for forensic report(s).' }
        Write-Host "Forensic report(s) committed and pushed to $Remote/$branch."
    }
} finally {
    Pop-Location
}
