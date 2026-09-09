param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$expectedBranch = 'codex/v104-raven-production'
$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $expectedBranch) {
    throw "Expected branch '$expectedBranch', found '$branch'."
}

$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -eq 'GoW' -or $_.ProcessName -eq 'GodOfWar'
})
if ($running.Count -gt 0) { throw 'God of War is running. Close it before offline assembly.' }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }
$builder = Join-Path $PSScriptRoot 'build-nornir-candidate3-offline.py'
$test = Join-Path $PSScriptRoot 'test_nornir_candidate3.py'
$verify = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
foreach ($required in @($builder, $test, $verify)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required tool: $required" }
}

$work = [IO.Path]::GetFullPath((Join-Path $repo 'build\v0.10.4-nornir-candidate3\offline'))
$repoPrefix = $repo.TrimEnd('\') + '\'
if (-not $work.StartsWith($repoPrefix, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing output cleanup outside repository: $work"
}

& $python.Source -m py_compile $builder $test
if ($LASTEXITCODE -ne 0) { throw 'Candidate 3 Python syntax check failed.' }

Write-Host 'Verify frozen Raven before Candidate 3 assembly...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verify -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven verification failed before Candidate 3 assembly.' }

if (Test-Path -LiteralPath $work) {
    Remove-Item -LiteralPath $work -Recurse -Force
}

Write-Host 'Build Candidate 3 offline from frozen Raven...'
& $python.Source $builder --game-root $GameRoot --repo-root $repo --output-dir $work
if ($LASTEXITCODE -ne 0) { throw 'Candidate 3 offline builder failed.' }

Write-Host 'Run Candidate 3 acceptance proof...'
& $python.Source $test --repo-root $repo --game-root $GameRoot
if ($LASTEXITCODE -ne 0) { throw 'Candidate 3 acceptance proof failed.' }

Write-Host 'Run nearby WAD regression tests...'
& $python.Source (Join-Path $PSScriptRoot 'test_nornir_texture_reversibility.py')
if ($LASTEXITCODE -ne 0) { throw 'Nornir texture reversibility regression failed.' }
& $python.Source (Join-Path $PSScriptRoot 'test_nornir_mg_accounting.py')
if ($LASTEXITCODE -ne 0) { throw 'Nornir MG accounting regression failed.' }
& $python.Source (Join-Path $PSScriptRoot 'test_wad_loader_bookkeeping.py')
if ($LASTEXITCODE -ne 0) { throw 'WAD loader bookkeeping regression failed.' }

Write-Host 'Verify frozen Raven after Candidate 3 assembly...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verify -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven verification failed after Candidate 3 assembly.' }

Write-Host 'NORNIR_CANDIDATE3_OFFLINE_GATE_PASSED'
Write-Host '  Candidate 3 built outside game: true'
Write-Host '  stock Dock/BoatDock definitions changed: false'
Write-Host '  opaque MG payload bytes changed: false'
Write-Host '  frozen Raven changed: false'
Write-Host '  runtime installer created: false'
Write-Host '  runtime install allowed: false'
