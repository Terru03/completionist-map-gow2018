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

Write-Host 'Checking Candidate 3 archived proof remains offline-only and pinned...'
$proof = Get-Content -LiteralPath $proofPath -Raw | ConvertFrom-Json
if ($proof.result -ne 'NORNIR_CANDIDATE3_OFFLINE_ASSEMBLED') { throw 'Unexpected Candidate 3 proof result.' }
if ($proof.candidate3.wad.candidate3_sha256 -ne '90391a2841d3a9ad889b95d5c17fc0ee09de803a57675b6d237a98051b08c660') { throw 'Candidate 3 WAD hash changed.' }
if ($proof.candidate3.runtime_install_allowed -or $proof.safety.runtime_install_allowed) { throw 'Candidate 3 proof must remain runtime_install_allowed=false.' }
if ($proof.proofs.candidate2_used_as_input) { throw 'Candidate 2 must not be an input to Candidate 3.' }
if ($proof.candidate3.wad.model_groups.opaque_mg_payload_bytes_changed) { throw 'Opaque MG payload mutation detected.' }
if ($proof.candidate3.wad.preservation.stock_dock_and_boatdock_definitions_mutated) { throw 'Stock Dock/BoatDock mutation detected.' }
if (-not $proof.proofs.raven_resources_preserved) { throw 'Raven preservation proof missing.' }
if (@($proof.candidate3.files.PSObject.Properties).Count -ne 10) { throw 'Candidate 3 proof does not contain exactly ten files.' }

Write-Host 'Running transaction engine only against a temporary fake game root...'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $selfTest | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Candidate 3 transaction self-test failed.' }

Write-Host ''
Write-Host 'NORNIR_RUNTIME_CANDIDATE3_INSTALLER_OFFLINE_GATE_PASSED'
Write-Host '  PowerShell syntax parsed: true'
Write-Host '  Candidate 3 proof remains offline-only: true'
Write-Host '  exact ten-file manifest pinned: true'
Write-Host '  transaction success/rollback fake-root proof: passed'
Write-Host '  automatic partial-failure rollback fake-root proof: passed'
Write-Host '  tamper refusal fake-root proof: passed'
Write-Host '  installed God of War files written: false'
Write-Host '  Candidate 3 runtime test performed: false'
Write-Host '  next: human review, then explicit -ConfirmRuntimeTest field install if approved'
