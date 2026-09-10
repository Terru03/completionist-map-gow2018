param(
    [string]$ReportPath = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$installer = Join-Path $PSScriptRoot 'raven-uid-compass-routing-runtime.ps1'
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) {
    throw "Missing UID-routing installer: $installer"
}
. $installer -LibraryOnly

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Write-Bytes([string]$Path, [byte[]]$Bytes) {
    New-Item -ItemType Directory -Force -Path (Split-Path $Path -Parent) | Out-Null
    [IO.File]::WriteAllBytes($Path, $Bytes)
}

function Snapshot([string]$Root) {
    $result = [ordered]@{}
    foreach ($name in $files.Keys) {
        $path = Resolve-SafeChildPath -Root $Root -Relative ([string]$files[$name]) -Label 'fixture file'
        $result[$name] = [ordered]@{
            exists = Test-Path -LiteralPath $path -PathType Leaf
            sha256 = if (Test-Path -LiteralPath $path -PathType Leaf) { Get-Sha256 $path } else { $null }
        }
    }
    return $result
}

function Assert-Snapshot([string]$Root, [System.Collections.IDictionary]$Expected) {
    foreach ($name in $files.Keys) {
        $path = Resolve-SafeChildPath -Root $Root -Relative ([string]$files[$name]) -Label 'fixture file'
        if ([bool]$Expected[$name].exists) {
            Assert-True (Test-Path -LiteralPath $path -PathType Leaf) "Restored file missing: $name"
            Assert-True ((Get-Sha256 $path) -eq [string]$Expected[$name].sha256) "Restored SHA differs: $name"
        }
        else {
            Assert-True (-not (Test-Path -LiteralPath $path)) "Restored file should be absent: $name"
        }
    }
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('completionist-raven-uid-routing-' + [Guid]::NewGuid().ToString('N'))
$fakeGame = Join-Path $tempRoot 'fake-game'
$fakeCandidate = Join-Path $tempRoot 'candidate'
$fakeState = Join-Path $tempRoot 'state'
$fakeActive = Join-Path $fakeState 'active.json'
Assert-True ([IO.Path]::GetFullPath($tempRoot).StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()))) 'Fixture root escaped temp directory.'
Assert-True ([IO.Path]::GetFullPath($fakeState).StartsWith([IO.Path]::GetFullPath($tempRoot) + [IO.Path]::DirectorySeparatorChar)) 'State root escaped fixture.'
New-Item -ItemType Directory -Force -Path $fakeGame, $fakeCandidate, $fakeState | Out-Null

try {
    $fixtureShas = [ordered]@{}
    $index = 0
    foreach ($name in $files.Keys) {
        $relative = [string]$files[$name]
        $candidatePath = Resolve-SafeChildPath -Root $fakeCandidate -Relative $relative -Label 'fixture candidate'
        Write-Bytes -Path $candidatePath -Bytes ([Text.Encoding]::UTF8.GetBytes("uid-routing-candidate-$index-$name`n"))
        $fixtureShas[$name] = Get-Sha256 $candidatePath
        if (($index % 2) -eq 0) {
            $gamePath = Resolve-SafeChildPath -Root $fakeGame -Relative $relative -Label 'fixture game'
            Write-Bytes -Path $gamePath -Bytes ([Text.Encoding]::UTF8.GetBytes("uid-routing-baseline-$index-$name`n"))
        }
        $index++
    }
    $baseline = Snapshot -Root $fakeGame

    # Clean success path: all four approved files install and restore exactly.
    $installed = Invoke-TransactionalInstall -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $fixtureShas -CandidateLabel 'raven-uid-routing-self-test' -RepoBranch 'self-test' -RepoHead 'self-test' -ProofPath 'self-test'
    Assert-True ($installed.status -eq 'installed') 'Success path did not reach installed state.'
    Assert-True (@($installed.entries).Count -eq 4) 'Success transaction does not contain four files.'
    Assert-True ([bool]$installed.safety.backup_complete_before_first_game_write) 'Backup-before-write proof missing.'
    Restore-State -Manifest $installed -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -ProofPath 'self-test' -FileMap $files -CandidateShas $fixtureShas -CandidateLabel 'raven-uid-routing-self-test' -RepoBranch 'self-test' -CheckInstalled $true -Force $false
    Assert-Snapshot -Root $fakeGame -Expected $baseline

    # Inject failure after two writes. The engine must automatically restore baseline.
    Remove-Item -LiteralPath $fakeState -Recurse -Force
    New-Item -ItemType Directory -Force -Path $fakeState | Out-Null
    $failureCaught = $false
    try {
        Invoke-TransactionalInstall -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $fixtureShas -CandidateLabel 'raven-uid-routing-self-test' -RepoBranch 'self-test' -RepoHead 'self-test' -ProofPath 'self-test' -FailureInjectionAfter 2 | Out-Null
    }
    catch { $failureCaught = $_.Exception.Message -like '*automatically rolled back*' }
    Assert-True $failureCaught 'Injected partial failure did not automatically roll back.'
    Assert-Snapshot -Root $fakeGame -Expected $baseline

    # Simulate abrupt interruption with one file installed and the next write started.
    Remove-Item -LiteralPath $fakeState -Recurse -Force
    New-Item -ItemType Directory -Force -Path $fakeState | Out-Null
    $interrupted = New-TransactionManifest -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $fixtureShas -CandidateLabel 'raven-uid-routing-self-test' -RepoBranch 'self-test' -RepoHead 'self-test' -ProofPath 'self-test'
    $interrupted.status = 'installing'
    Save-TransactionManifest -Manifest $interrupted -Active $fakeActive
    $firstInterrupted = @($interrupted.entries)[0]
    $firstInterrupted.write_state = 'write-started'
    Save-TransactionManifest -Manifest $interrupted -Active $fakeActive
    $firstSource = Resolve-SafeChildPath -Root $fakeCandidate -Relative ([string]$firstInterrupted.relative) -Label 'fixture candidate'
    $firstDest = Resolve-SafeChildPath -Root $fakeGame -Relative ([string]$firstInterrupted.relative) -Label 'fixture game'
    Copy-Verified -Source $firstSource -Destination $firstDest -ExpectedSha ([string]$firstInterrupted.candidate_sha256)
    $firstInterrupted.write_state = 'installed'
    @($interrupted.entries)[1].write_state = 'write-started'
    Save-TransactionManifest -Manifest $interrupted -Active $fakeActive

    $recovery = Get-ValidatedActiveTransaction -Active $fakeActive -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -ProofPath 'self-test' -FileMap $files -CandidateShas $fixtureShas -CandidateLabel 'raven-uid-routing-self-test' -RepoBranch 'self-test'
    $checkInstalled = Get-UidRoutingRollbackCheckInstalled -Status ([string]$recovery.status)
    Assert-True (-not $checkInstalled) 'Interrupted recovery unexpectedly requires fully installed bytes.'
    Restore-State -Manifest $recovery -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -ProofPath 'self-test' -FileMap $files -CandidateShas $fixtureShas -CandidateLabel 'raven-uid-routing-self-test' -RepoBranch 'self-test' -CheckInstalled $checkInstalled -Force $false
    $recovery.status = 'rolled-back'
    Save-TransactionManifest -Manifest $recovery -Active $fakeActive
    Assert-Snapshot -Root $fakeGame -Expected $baseline

    # Normal rollback must refuse bytes changed after installation; no forced rollback.
    Remove-Item -LiteralPath $fakeState -Recurse -Force
    New-Item -ItemType Directory -Force -Path $fakeState | Out-Null
    $tamper = Invoke-TransactionalInstall -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $fixtureShas -CandidateLabel 'raven-uid-routing-self-test' -RepoBranch 'self-test' -RepoHead 'self-test' -ProofPath 'self-test'
    $first = @($tamper.entries)[0]
    $tamperedPath = Resolve-SafeChildPath -Root $fakeGame -Relative ([string]$first.relative) -Label 'fixture game'
    [IO.File]::AppendAllText($tamperedPath, 'tampered')
    $tamperRefused = $false
    try {
        Restore-State -Manifest $tamper -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -ProofPath 'self-test' -FileMap $files -CandidateShas $fixtureShas -CandidateLabel 'raven-uid-routing-self-test' -RepoBranch 'self-test' -CheckInstalled $true -Force $false
    }
    catch { $tamperRefused = $_.Exception.Message -like '*changed since*' }
    Assert-True $tamperRefused 'Normal rollback did not refuse changed installed bytes.'

    $report = [ordered]@{
        schema = 1
        result = 'RAVEN_UID_COMPASS_ROUTING_TRANSACTION_SELF_TEST_PASSED'
        tested_installer = 'tools/v0.10.4/raven-uid-compass-routing-runtime.ps1'
        derived_engine = 'tools/v0.10.4/nornir-runtime-candidate3.ps1@036628c'
        derived_engine_sha256 = $expectedEngineSha
        approved_file_count = 4
        proofs = [ordered]@{
            exact_036628c_engine_pinned = $true
            exact_success_install = $true
            backup_complete_before_first_write = $true
            exact_success_rollback = $true
            partial_failure_automatic_rollback = $true
            abrupt_interruption_normal_recovery = $true
            tampered_install_refused_by_normal_rollback = $true
            force_rollback_used = $false
        }
        safety = [ordered]@{
            fake_game_root_only = $true
            installed_god_of_war_written = $false
            god_of_war_launched = $false
            saves_progression_marker_state_written = $false
            runtime_installer_executed_against_game = $false
        }
    }

    if ([string]::IsNullOrWhiteSpace($ReportPath)) {
        $ReportPath = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'archive\field-logs\completionist-v104-raven-uid-compass-routing-transaction-self-test.json'
    }
    Write-JsonAtomic -Value $report -Path $ReportPath
    Write-Host 'RAVEN_UID_COMPASS_ROUTING_TRANSACTION_SELF_TEST_PASSED'
    Write-Host '  fake root only: true'
    Write-Host '  four-file install/rollback exact: true'
    Write-Host '  partial failure auto-rollback exact: true'
    Write-Host '  abrupt interruption no-force recovery exact: true'
    Write-Host '  tamper refusal: true'
    Write-Host '  force rollback used: false'
    Write-Host '  real game files written: false'
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
