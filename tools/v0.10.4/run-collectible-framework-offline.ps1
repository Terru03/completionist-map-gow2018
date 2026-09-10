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
if ($running.Count -gt 0) { throw 'God of War is running. Close it before offline proof.' }
if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) {
    throw "God of War root not found: $GameRoot"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { throw 'Python 3 is required.' }
$framework = Join-Path $PSScriptRoot 'collectible_framework.py'
$tests = Join-Path $PSScriptRoot 'test_collectible_framework.py'
$proof = Join-Path $PSScriptRoot 'prove-collectible-framework-offline.py'
$verify = Join-Path $PSScriptRoot 'verify-raven-production-state.ps1'
foreach ($required in @($framework, $tests, $proof, $verify)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing required tool: $required"
    }
}

& $python.Source -m py_compile $framework $tests $proof
if ($LASTEXITCODE -ne 0) { throw 'Framework Python syntax check failed.' }

Write-Host 'Verify frozen Raven before framework proof...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verify -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven verification failed before framework proof.' }

Write-Host 'Run collectible framework validator suite...'
$env:COMPLETIONIST_GAME_ROOT = $GameRoot
& $python.Source $tests
if ($LASTEXITCODE -ne 0) { throw 'Collectible framework tests failed.' }

Write-Host 'Build synthetic framework proof without retired Nornir inputs...'
& $python.Source $proof --game-root $GameRoot --repo-root $repo
if ($LASTEXITCODE -ne 0) { throw 'Collectible framework proof failed.' }

Write-Host 'Verify frozen Raven after framework proof...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $verify -GameRoot $GameRoot | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven verification failed after framework proof.' }

Write-Host 'COLLECTIBLE_FRAMEWORK_OFFLINE_GATE_PASSED'
Write-Host '  Raven changed: false'
Write-Host '  retired Nornir construction used: false'
Write-Host '  synthetic registry-only build: true'
Write-Host '  installed game writes: false'
Write-Host '  runtime install allowed: false'
