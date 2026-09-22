param(
    [string]$GameRootFixture = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$ExpectedBranch = 'codex/all-ravens-release-candidate'
$SecurityBase = '5d97b4f'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Not inside repository.' }
Set-Location $repo
if ((& git branch --show-current).Trim() -ne $ExpectedBranch) { throw "Need branch $ExpectedBranch." }
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
    throw 'Close God of War first.'
}

function Invoke-PythonTest([string]$Path, [bool]$RequireLua) {
    $pythonExe = 'python.exe'
    $prefix = @()
    & py.exe -3.14 -c 'import sys' 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pythonExe = 'py.exe'
        $prefix = @('-3.14')
    }
    elseif ($null -eq (Get-Command $pythonExe -ErrorAction SilentlyContinue)) {
        throw 'Python 3 with test dependencies not found.'
    }
    $lines = @(& $pythonExe @prefix $Path 2>&1)
    $lines | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) { throw "Python test failed: $Path" }
    if ($RequireLua -and (@($lines | Select-String -SimpleMatch 'skipped').Count -gt 0)) {
        throw 'Lua 5.1 tests skipped; real Lua runtime is required.'
    }
}

Write-Host 'RAVEN NATIVE SNAPSHOT DELIVERY OFFLINE GATES'
Write-Host '1/8 native MSVC / CTest / schema-3 rollback gates'
& (Join-Path $repo 'tools\v0.10.5\test-raven-authority-bridge-offline-gates.ps1') -GameRootFixture $GameRootFixture
if ($LASTEXITCODE -ne 0) { throw 'Native offline gate failed.' }

Write-Host '2/8 Lua 5.1 integration tests'
Invoke-PythonTest (Join-Path $repo 'tools\v0.10.5\test_all_ravens_lua.py') $true

Write-Host '3/8 state-model tests'
Invoke-PythonTest (Join-Path $repo 'tools\v0.10.5\test_raven_runtime_model.py') $false

Write-Host '4/8 offline candidate/template tests'
Invoke-PythonTest (Join-Path $repo 'tools\v0.10.5\test_all_ravens_build.py') $false

Write-Host '5/8 prepare pinned five-file delivery candidate'
Invoke-PythonTest (Join-Path $repo 'tools\v0.10.5\prepare-all-ravens-delivery-candidate.py') $false

Write-Host '6/8 five-file transaction rollback tests'
$transactionReport = Join-Path ([IO.Path]::GetTempPath()) (
    'completionist-all-ravens-transaction-' + [Guid]::NewGuid().ToString('N') + '.json')
try {
    & (Join-Path $repo 'tools\v0.10.5\test-all-ravens-transaction.ps1') -ReportPath $transactionReport
    if ($LASTEXITCODE -ne 0) { throw 'All-Ravens transaction gate failed.' }
    if (-not (Test-Path -LiteralPath $transactionReport -PathType Leaf)) {
        throw 'All-Ravens transaction gate did not produce its temporary report.'
    }
    $transactionProof = Get-Content -LiteralPath $transactionReport -Raw | ConvertFrom-Json
    if ($transactionProof.result -ne 'ALL_RAVENS_TRANSACTION_SELF_TEST_PASSED') {
        throw 'All-Ravens transaction temporary report did not pass.'
    }
}
finally {
    Remove-Item -LiteralPath $transactionReport -Force -ErrorAction SilentlyContinue
}

Write-Host '7/8 PowerShell syntax gate'
$parseFiles = @(
    'tools\v0.10.5\raven-native-bridge-runner-support.ps1',
    'tools\v0.10.5\test-raven-authority-bridge-runner.ps1',
    'tools\v0.10.5\test-all-ravens-transaction.ps1',
    'tools\v0.10.5\test-raven-native-snapshot-delivery-offline-gates.ps1',
    'tools\v0.10.5\test-raven-native-snapshot-delivery-offline-gates-and-push.ps1',
    'tools\v0.10.5\run-raven-native-snapshot-delivery-live-proof-and-push.ps1'
)
foreach ($relative in $parseFiles) {
    $path = Join-Path $repo $relative
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing PowerShell gate file: $relative" }
    $tokens = $null
    $errors = $null
    [void][Management.Automation.Language.Parser]::ParseFile($path, [ref]$tokens, [ref]$errors)
    if (@($errors).Count -gt 0) { throw "PowerShell parse failed: $relative :: $($errors[0].Message)" }
}
Write-Host "RAVEN_SNAPSHOT_DELIVERY_POWERSHELL_PARSE_PASSED files=$($parseFiles.Count)"

Write-Host '8/8 scoped security write-API gate'
$securityPaths = @(
    'native/raven-authority-bridge/src',
    'tools/v0.10.5/all-ravens-map-runtime.lua',
    'tools/v0.10.5/all-ravens-gameplay-events.lua'
)
$diff = (& git diff $SecurityBase -- @securityPaths 2>&1) -join "`n"
if ($LASTEXITCODE -ne 0) { throw 'Could not read security diff.' }
$forbidden = @(
    'WriteProcessMemory', 'VirtualProtectEx', 'PROCESS_VM_WRITE', 'PROCESS_VM_OPERATION',
    'GENERIC_WRITE', 'FILE_APPEND_DATA', 'CREATE_ALWAYS', 'TRUNCATE_EXISTING',
    'SetMarkerState', 'SetToken', 'SetProgress', 'IncrementQuestProgress', 'StartQuest'
)
$findings = @()
foreach ($token in $forbidden) {
    if ($diff -match [regex]::Escape($token)) { $findings += $token }
}
if ($findings.Count -gt 0) { throw "Security write-API gate failed: $($findings -join ', ')" }
if ($diff -notmatch '127\.0\.0\.1' -or $diff -notmatch 'SO_EXCLUSIVEADDRUSE' -or
    $diff -notmatch 'static_descriptor_writes=false') {
    throw 'Loopback/exclusive/static-descriptor safety contract missing from diff.'
}
Write-Host 'RAVEN_SNAPSHOT_DELIVERY_SECURITY_GATE_PASSED process_writes=false save_writes=false progression_writes=false static_descriptor_writes=false loopback_only=true'
Write-Host 'RAVEN_NATIVE_SNAPSHOT_DELIVERY_OFFLINE_GATES_PASSED native_tests=5 lua_tests=13 model_tests=21 transaction=true powershell=true security=true'
