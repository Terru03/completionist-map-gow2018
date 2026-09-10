param()

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$expectedBranch = 'codex/v104-raven-production'
$branch = (& git -C $repo branch --show-current).Trim()
if ($LASTEXITCODE -ne 0 -or $branch -ne $expectedBranch) {
    throw "Expected branch '$expectedBranch', found '$branch'."
}

$installer = Join-Path $PSScriptRoot 'nornir-runtime-candidate3.ps1'
$selfTest = Join-Path $PSScriptRoot 'test-nornir-runtime-candidate3-transaction.ps1'
$proofPath = Join-Path $repo 'archive\field-logs\completionist-v104-nornir-candidate3-offline-reconstruction.json'
foreach ($required in @($installer, $selfTest, $proofPath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}

Write-Host 'Parsing Candidate 3 installer and self-test with the PowerShell parser...'
foreach ($script in @($installer, $selfTest)) {
    $tokens = $null
    $errors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($script, [ref]$tokens, [ref]$errors)
    if (@($errors).Count -gt 0) {
        $detail = @($errors | ForEach-Object { $_.Message }) -join '; '
        throw "PowerShell syntax errors in $script : $detail"
    }
}
$installerText = Get-Content -LiteralPath $installer -Raw
if ($installerText -match 'nornir-runtime-candidate2\.ps1|v0\.10\.4-nornir-runtime-candidate2') {
    throw 'Candidate 3 installer references a retired Candidate 2 artifact path.'
}

Write-Host 'Checking Candidate 3 archived proof and current build output remain exact, offline-only, and pinned...'
. $installer -LibraryOnly
$validatedCandidate = Assert-Candidate3
if (@($validatedCandidate.shas.Keys).Count -ne 10) { throw 'Candidate 3 validation did not return exactly ten files.' }

Write-Host 'Running transaction engine only against a temporary fake game root...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $selfTest | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Candidate 3 transaction self-test failed.' }

Write-Host ''
Write-Host 'NORNIR_RUNTIME_CANDIDATE3_INSTALLER_OFFLINE_GATE_PASSED'
Write-Host '  PowerShell syntax parsed: true'
Write-Host '  Candidate 3 proof remains offline-only: true'
Write-Host '  exact ten-file manifest pinned: true'
Write-Host '  current Candidate 3 build output SHA-verified: true'
Write-Host '  Candidate 2 artifact paths referenced: false'
Write-Host '  transaction success/rollback fake-root proof: passed'
Write-Host '  automatic partial-failure rollback fake-root proof: passed'
Write-Host '  tamper refusal fake-root proof: passed'
Write-Host '  corrupt-backup all-or-nothing fake-root proof: passed'
Write-Host '  pending-entry, stale-active, and stale-force fake-root guards: passed'
Write-Host '  manifest and path-topology fake-root guards: passed'
Write-Host '  installed God of War files written: false'
Write-Host '  Candidate 3 runtime test performed: false'
Write-Host '  next: human review, then explicit -ConfirmRuntimeTest field install if approved'
