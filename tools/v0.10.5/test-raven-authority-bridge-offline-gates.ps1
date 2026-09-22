param(
    [string]$GameRootFixture = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$ExpectedBranch = 'codex/all-ravens-release-candidate'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo

if ((& git branch --show-current).Trim() -ne $ExpectedBranch) {
    throw "Need branch $ExpectedBranch."
}
if (@(& git diff --cached --name-only).Count -gt 0) {
    throw 'Staged changes exist. Refuse offline gate.'
}
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
    throw 'Close God of War first.'
}

$runnerTest = Join-Path $repo 'tools\v0.10.5\test-raven-authority-bridge-runner.ps1'
$buildScript = Join-Path $repo 'tools\v0.10.5\build-raven-authority-bridge.ps1'
$installTest = Join-Path $repo 'tools\v0.10.5\test-raven-authority-bridge-install.ps1'
$operationTest = Join-Path $repo 'tools\v0.10.5\test-raven-authority-bridge-operation-synthetic.ps1'
$fixtureExe = Join-Path $GameRootFixture 'GoW.exe'
$fixtureVersion = Join-Path $GameRootFixture 'version.dll'

foreach ($required in @($runnerTest,$buildScript,$installTest,$operationTest,$fixtureExe,$fixtureVersion)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Need offline-gate file: $required"
    }
}

Write-Host 'RAVEN DXGI OFFLINE GATES'
Write-Host '1/4 runner regressions'
& $runnerTest
if ($LASTEXITCODE -ne 0) { throw 'Runner regression gate failed.' }

Write-Host '2/4 clean native build + five CTest targets'
& $buildScript -Clean
if ($LASTEXITCODE -ne 0) { throw 'Native build/test gate failed.' }

Write-Host '3/4 temp-root schema-3 DXGI install/rollback/recovery suite'
& $installTest -GameRootFixture $GameRootFixture
if ($LASTEXITCODE -ne 0) { throw 'Install/rollback/recovery gate failed.' }

Write-Host '4/4 fixture-free interrupted bridge operation recovery'
& $operationTest
if ($LASTEXITCODE -ne 0) { throw 'Bridge operation journal recovery gate failed.' }

Write-Host 'RAVEN_DXGI_OFFLINE_GATES_PASSED native_tests=5 runner=true install_rollback_recovery=true operation_journal_recovery=true real_game_install=false version_dll_writes=false save_writes=false progression_writes=false'
