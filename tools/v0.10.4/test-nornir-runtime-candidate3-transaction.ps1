param(
    [string]$ReportPath
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$installer = Join-Path $PSScriptRoot 'nornir-runtime-candidate3.ps1'
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw "Missing installer: $installer" }

. $installer -LibraryOnly

function Assert-True([bool]$Value, [string]$Message) {
    if (-not $Value) { throw $Message }
}

function Write-Bytes([string]$Path, [byte[]]$Bytes) {
    New-Item -ItemType Directory -Force -Path (Split-Path $Path -Parent) | Out-Null
    [IO.File]::WriteAllBytes($Path, $Bytes)
}

function Snapshot-Fixture([string]$Root, [System.Collections.IDictionary]$FileMap) {
    $snapshot = [ordered]@{}
    foreach ($name in $FileMap.Keys) {
        $relative = [string]$FileMap[$name]
        $path = Resolve-SafeChildPath -Root $Root -Relative $relative -Label 'fixture path'
        if (Test-Path -LiteralPath $path -PathType Leaf) {
            $snapshot[$name] = [ordered]@{ exists = $true; sha256 = Get-Sha256 $path }
        }
        else {
            $snapshot[$name] = [ordered]@{ exists = $false; sha256 = $null }
        }
    }
    return $snapshot
}

function Assert-Snapshot([string]$Root, [System.Collections.IDictionary]$FileMap, [System.Collections.IDictionary]$Snapshot, [string]$Label) {
    foreach ($name in $FileMap.Keys) {
        $relative = [string]$FileMap[$name]
        $path = Resolve-SafeChildPath -Root $Root -Relative $relative -Label 'fixture path'
        $expected = $Snapshot[$name]
        if ([bool]$expected.exists) {
            Assert-True (Test-Path -LiteralPath $path -PathType Leaf) "$Label missing restored file: $name"
            Assert-True ((Get-Sha256 $path) -eq [string]$expected.sha256) "$Label SHA mismatch: $name"
        }
        else {
            Assert-True (-not (Test-Path -LiteralPath $path)) "$Label expected absent file: $name"
        }
    }
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('completionist-candidate3-selftest-' + [Guid]::NewGuid().ToString('N'))
$fakeGame = Join-Path $tempRoot 'fake-game'
$fakeCandidate = Join-Path $tempRoot 'candidate'
$fakeState = Join-Path $tempRoot 'state'
$fakeActive = Join-Path $fakeState 'active.json'
New-Item -ItemType Directory -Force -Path $fakeGame, $fakeCandidate, $fakeState | Out-Null

try {
    $candidateShas = [ordered]@{}
    $index = 0
    foreach ($name in $files.Keys) {
        $relative = [string]$files[$name]
        $candidatePath = Resolve-SafeChildPath -Root $fakeCandidate -Relative $relative -Label 'fixture candidate'
        $candidateBytes = [Text.Encoding]::UTF8.GetBytes("candidate3-fixture-$index-$name`n")
        Write-Bytes -Path $candidatePath -Bytes $candidateBytes
        $candidateShas[$name] = Get-Sha256 $candidatePath

        if (($index % 2) -eq 0) {
            $gamePath = Resolve-SafeChildPath -Root $fakeGame -Relative $relative -Label 'fixture game'
            $baselineBytes = [Text.Encoding]::UTF8.GetBytes("baseline-fixture-$index-$name`n")
            Write-Bytes -Path $gamePath -Bytes $baselineBytes
        }
        $index++
    }

    $baseline = Snapshot-Fixture -Root $fakeGame -FileMap $files

    # Success path: backup all destinations, install all candidate files, verify, rollback exact.
    $success = Invoke-TransactionalInstall -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'candidate3-self-test' -RepoBranch 'self-test' -RepoHead 'self-test' -ProofPath 'self-test'
    Assert-True ($success.status -eq 'installed') 'Success-path transaction did not reach installed state.'
    Assert-True (@($success.entries).Count -eq 10) 'Success-path transaction did not contain ten entries.'
    Assert-True ([bool]$success.safety.backup_complete_before_first_game_write) 'Backup-before-write safety flag missing.'
    foreach ($entry in @($success.entries)) {
        $dest = Resolve-SafeChildPath -Root $fakeGame -Relative ([string]$entry.relative) -Label 'fixture game'
        Assert-True ((Get-Sha256 $dest) -eq ([string]$entry.candidate_sha256)) "Installed fixture SHA mismatch: $($entry.name)"
    }
    Restore-State -Manifest $success -Game $fakeGame -CheckInstalled $true -Force $false
    Assert-Snapshot -Root $fakeGame -FileMap $files -Snapshot $baseline -Label 'success rollback'

    # Failure path: inject a failure after three real writes and demand automatic exact rollback.
    Remove-Item -LiteralPath $fakeState -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $fakeState | Out-Null
    $failureCaught = $false
    try {
        Invoke-TransactionalInstall -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'candidate3-self-test-failure' -RepoBranch 'self-test' -RepoHead 'self-test' -ProofPath 'self-test' -FailureInjectionAfter 3 | Out-Null
    }
    catch {
        $failureCaught = $_.Exception.Message -like '*automatically rolled back*'
    }
    Assert-True $failureCaught 'Injected install failure did not report automatic rollback.'
    Assert-Snapshot -Root $fakeGame -FileMap $files -Snapshot $baseline -Label 'automatic rollback'
    $failedActive = Get-Content -LiteralPath $fakeActive -Raw | ConvertFrom-Json
    Assert-True ($failedActive.status -eq 'rolled-back-after-install-failure') 'Failure transaction status was not rolled-back-after-install-failure.'

    # Tamper path: normal rollback must refuse altered installed bytes; forced rollback may restore after review.
    Remove-Item -LiteralPath $fakeState -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $fakeState | Out-Null
    $tamper = Invoke-TransactionalInstall -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'candidate3-self-test-tamper' -RepoBranch 'self-test' -RepoHead 'self-test' -ProofPath 'self-test'
    $first = @($tamper.entries)[0]
    $tamperedPath = Resolve-SafeChildPath -Root $fakeGame -Relative ([string]$first.relative) -Label 'fixture game'
    [IO.File]::AppendAllText($tamperedPath, 'tampered')
    $tamperRefused = $false
    try {
        Restore-State -Manifest $tamper -Game $fakeGame -CheckInstalled $true -Force $false
    }
    catch {
        $tamperRefused = $_.Exception.Message -like '*changed since Candidate 3 install*'
    }
    Assert-True $tamperRefused 'Rollback did not refuse a tampered installed file.'
    Restore-State -Manifest $tamper -Game $fakeGame -CheckInstalled $true -Force $true
    Assert-Snapshot -Root $fakeGame -FileMap $files -Snapshot $baseline -Label 'forced reviewed rollback'

    $report = [ordered]@{
        schema = 1
        result = 'NORNIR_RUNTIME_CANDIDATE3_TRANSACTION_SELF_TEST_PASSED'
        tested_installer = 'tools/v0.10.4/nornir-runtime-candidate3.ps1'
        approved_file_count = @($files.Keys).Count
        proofs = [ordered]@{
            success_install_all_candidate_shas_exact = $true
            backups_complete_before_first_write = $true
            exact_success_rollback = $true
            injected_partial_install_automatically_rolled_back = $true
            exact_automatic_failure_rollback = $true
            tampered_install_refused_without_force = $true
            forced_reviewed_rollback_restored_exact_baseline = $true
            preexisting_and_newly_created_destinations_both_tested = $true
        }
        safety = [ordered]@{
            fake_game_root_only = $true
            installed_god_of_war_written = $false
            god_of_war_launched = $false
            saves_progression_marker_state_written = $false
            candidate3_runtime_install_performed = $false
        }
    }

    if ([string]::IsNullOrWhiteSpace($ReportPath)) {
        $ReportPath = Join-Path $repo 'build\v0.10.4-nornir-runtime-candidate3\transaction-self-test.json'
    }
    Write-JsonAtomic -Value $report -Path $ReportPath
    Write-Host 'NORNIR_RUNTIME_CANDIDATE3_TRANSACTION_SELF_TEST_PASSED'
    Write-Host '  fake game root only: true'
    Write-Host '  success install/rollback exact: true'
    Write-Host '  partial failure auto-rollback exact: true'
    Write-Host '  tamper refusal: true'
    Write-Host '  real God of War files written: false'
    Write-Host "  report: $ReportPath"
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
