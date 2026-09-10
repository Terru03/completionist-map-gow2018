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

function Restore-Fixture([object]$Manifest, [bool]$CheckInstalled, [bool]$Force) {
    Restore-State -Manifest $Manifest -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -ProofPath 'self-test' -FileMap $files -CandidateShas $candidateShas -CandidateLabel ([string]$Manifest.candidate) -RepoBranch 'self-test' -CheckInstalled $CheckInstalled -Force $Force
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
    $relativeProbe = Get-SafeRelativePath -Root $fakeCandidate -Path (Resolve-SafeChildPath -Root $fakeCandidate -Relative ([string]$files['r_ui.wad']) -Label 'fixture candidate') -Label 'fixture candidate'
    Assert-True ($relativeProbe -eq 'exec/wad/pc_le/r_ui.wad') 'Windows PowerShell-safe relative path is wrong.'
    $wrongGameRootRefused = $false
    try { Assert-GameRootIdentity -Game $fakeGame }
    catch { $wrongGameRootRefused = $_.Exception.Message -like '*God of War executable not found*' }
    Assert-True $wrongGameRootRefused 'Wrong game root without GoW.exe was accepted.'

    # Success path: backup all destinations, install all candidate files, verify, rollback exact.
    $success = Invoke-TransactionalInstall -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'candidate3-self-test' -RepoBranch 'self-test' -RepoHead 'self-test' -ProofPath 'self-test'
    Assert-True ($success.status -eq 'installed') 'Success-path transaction did not reach installed state.'
    Assert-True (@($success.entries).Count -eq 10) 'Success-path transaction did not contain ten entries.'
    Assert-True ([bool]$success.safety.backup_complete_before_first_game_write) 'Backup-before-write safety flag missing.'
    foreach ($entry in @($success.entries)) {
        $dest = Resolve-SafeChildPath -Root $fakeGame -Relative ([string]$entry.relative) -Label 'fixture game'
        Assert-True ((Get-Sha256 $dest) -eq ([string]$entry.candidate_sha256)) "Installed fixture SHA mismatch: $($entry.name)"
    }
    Restore-Fixture -Manifest $success -CheckInstalled $true -Force $false
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
        Restore-Fixture -Manifest $tamper -CheckInstalled $true -Force $false
    }
    catch {
        $tamperRefused = $_.Exception.Message -like '*changed since Candidate 3 install*'
    }
    Assert-True $tamperRefused 'Rollback did not refuse a tampered installed file.'
    Restore-Fixture -Manifest $tamper -CheckInstalled $true -Force $true
    Assert-Snapshot -Root $fakeGame -FileMap $files -Snapshot $baseline -Label 'forced reviewed rollback'

    # Bad backup must stop rollback before any game file changes.
    Remove-Item -LiteralPath $fakeState -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $fakeState | Out-Null
    $badBackup = Invoke-TransactionalInstall -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'candidate3-self-test-bad-backup' -RepoBranch 'self-test' -RepoHead 'self-test' -ProofPath 'self-test'
    $firstBackupEntry = @($badBackup.entries)[0]
    $firstBackupPath = Resolve-SafeChildPath -Root ([string]$badBackup.transaction_root) -Relative ([string]$firstBackupEntry.backup_relative) -Label 'fixture backup'
    [IO.File]::AppendAllText($firstBackupPath, 'corrupt')
    $badBackupRefused = $false
    try {
        Restore-Fixture -Manifest $badBackup -CheckInstalled $true -Force $false
    }
    catch {
        $badBackupRefused = $_.Exception.Message -like '*Backup SHA mismatch*'
    }
    Assert-True $badBackupRefused 'Rollback did not refuse a corrupt backup.'
    foreach ($entry in @($badBackup.entries)) {
        $dest = Resolve-SafeChildPath -Root $fakeGame -Relative ([string]$entry.relative) -Label 'fixture game'
        Assert-True ((Get-Sha256 $dest) -eq ([string]$entry.candidate_sha256)) "Bad-backup rollback changed a destination before full preflight: $($entry.name)"
    }
    $firstBackupBytes = [Text.Encoding]::UTF8.GetBytes("baseline-fixture-0-r_ui.wad`n")
    Write-Bytes -Path $firstBackupPath -Bytes $firstBackupBytes
    Restore-Fixture -Manifest $badBackup -CheckInstalled $true -Force $false
    Assert-Snapshot -Root $fakeGame -FileMap $files -Snapshot $baseline -Label 'bad backup repaired rollback'

    # Bad source SHA during backup phase must not create active state or write game files.
    Remove-Item -LiteralPath $fakeState -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $fakeState | Out-Null
    $badShas = [ordered]@{}
    foreach ($name in $candidateShas.Keys) { $badShas[$name] = $candidateShas[$name] }
    $badShas[@($badShas.Keys)[-1]] = '0' * 64
    $preManifestRefused = $false
    try {
        New-TransactionManifest -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $badShas -CandidateLabel 'candidate3-self-test-pre-manifest' -RepoBranch 'self-test' -RepoHead 'self-test' -ProofPath 'self-test' | Out-Null
    }
    catch {
        $preManifestRefused = $_.Exception.Message -like '*Candidate changed after proof validation*'
    }
    Assert-True $preManifestRefused 'Bad source SHA did not stop backup phase.'
    Assert-True (-not (Test-Path -LiteralPath $fakeActive)) 'Backup-phase failure created active state.'
    Assert-Snapshot -Root $fakeGame -FileMap $files -Snapshot $baseline -Label 'backup-phase failure'

    # Failure after manifest but before first write must not delete a late file on pending path.
    Remove-Item -LiteralPath $fakeState -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $fakeState | Out-Null
    $pendingName = @($files.Keys)[1]
    $pendingPath = Resolve-SafeChildPath -Root $fakeGame -Relative ([string]$files[$pendingName]) -Label 'fixture game'
    $preWriteFailureCaught = $false
    $preWriteFailure = {
        Write-Bytes -Path $pendingPath -Bytes ([Text.Encoding]::UTF8.GetBytes('late-file-before-first-write'))
        throw 'SELF_TEST_PRE_WRITE_FAILURE'
    }
    try {
        Invoke-TransactionalInstall -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'candidate3-self-test-pre-write' -RepoBranch 'self-test' -RepoHead 'self-test' -ProofPath 'self-test' -PreWriteValidation $preWriteFailure | Out-Null
    }
    catch {
        $preWriteFailureCaught = $_.Exception.Message -like '*automatically rolled back*'
    }
    Assert-True $preWriteFailureCaught 'Pre-write failure did not complete safe recovery.'
    Assert-True (Test-Path -LiteralPath $pendingPath -PathType Leaf) 'Recovery deleted file on entry installer never wrote.'
    Assert-True (([IO.File]::ReadAllText($pendingPath)) -eq 'late-file-before-first-write') 'Recovery changed file on entry installer never wrote.'
    $preWriteActive = Get-Content -LiteralPath $fakeActive -Raw | ConvertFrom-Json
    Assert-True ($preWriteActive.status -eq 'rolled-back-after-install-failure') 'Pre-write failure status is wrong.'
    Assert-True (@($preWriteActive.entries | Where-Object write_state -ne 'pending').Count -eq 0) 'Pre-write failure marked a pending entry written.'
    Remove-Item -LiteralPath $pendingPath -Force

    # Write-started new file with unknown bytes stays safe, even with force.
    Remove-Item -LiteralPath $fakeState -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $fakeState | Out-Null
    $uncertain = New-TransactionManifest -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'candidate3-self-test-uncertain' -RepoBranch 'self-test' -RepoHead 'self-test' -ProofPath 'self-test'
    $uncertainEntry = @($uncertain.entries | Where-Object { -not [bool]$_.existed_before })[0]
    $uncertainEntry.write_state = 'write-started'
    $uncertain.status = 'installing'
    Save-TransactionManifest -Manifest $uncertain -Active $fakeActive
    $uncertainPath = Resolve-SafeChildPath -Root $fakeGame -Relative ([string]$uncertainEntry.relative) -Label 'fixture game'
    Write-Bytes -Path $uncertainPath -Bytes ([Text.Encoding]::UTF8.GetBytes('not-candidate-bytes'))
    $uncertainRefused = $false
    try {
        Restore-Fixture -Manifest $uncertain -CheckInstalled $false -Force $true
    }
    catch {
        $uncertainRefused = $_.Exception.Message -like '*Refusing to remove non-Candidate 3 file*'
    }
    Assert-True $uncertainRefused 'Force rollback deleted an uncertain non-Candidate 3 file.'
    Assert-True (Test-Path -LiteralPath $uncertainPath -PathType Leaf) 'Uncertain file was deleted.'
    Remove-Item -LiteralPath $uncertainPath -Force

    # Manifest, status, topology, and reparse guards fail closed.
    Remove-Item -LiteralPath $fakeState -Recurse -Force -ErrorAction SilentlyContinue
    New-Item -ItemType Directory -Force -Path $fakeState | Out-Null
    $guardManifest = New-TransactionManifest -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'candidate3-self-test-guards' -RepoBranch 'self-test' -RepoHead 'self-test' -ProofPath 'self-test'
    $wrongRoot = $guardManifest | ConvertTo-Json -Depth 30 | ConvertFrom-Json
    $wrongRoot.transaction_root = Join-Path $tempRoot 'wrong-transaction-root'
    $wrongRootRefused = $false
    try {
        Assert-TransactionManifest -Manifest $wrongRoot -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -ProofPath 'self-test' -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'candidate3-self-test-guards' -RepoBranch 'self-test'
    }
    catch { $wrongRootRefused = $_.Exception.Message -like '*transaction root does not match*' }
    Assert-True $wrongRootRefused 'Wrong transaction root was accepted.'

    $missingEntry = $guardManifest | ConvertTo-Json -Depth 30 | ConvertFrom-Json
    $missingEntry.entries = @($missingEntry.entries | Select-Object -Skip 1)
    $missingEntryRefused = $false
    try {
        Assert-TransactionManifest -Manifest $missingEntry -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -ProofPath 'self-test' -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'candidate3-self-test-guards' -RepoBranch 'self-test'
    }
    catch { $missingEntryRefused = $_.Exception.Message -like '*exactly ten entries*' }
    Assert-True $missingEntryRefused 'Incomplete transaction file set was accepted.'

    foreach ($status in @('rolled-back','rolled-back-after-install-failure','unknown-status')) {
        $statusRefused = $false
        try { Assert-RollbackStatus -Status $status -Force $true }
        catch { $statusRefused = $true }
        Assert-True $statusRefused "Force rollback accepted stale or unknown status: $status"
    }

    # Active copy cannot hide a live transaction by claiming a terminal status.
    $staleActive = Get-Content -LiteralPath $fakeActive -Raw | ConvertFrom-Json
    $staleActive.status = 'rolled-back'
    Write-JsonAtomic -Value $staleActive -Path $fakeActive
    $trustedTransaction = Get-ValidatedActiveTransaction -Active $fakeActive -Game $fakeGame -Candidate $fakeCandidate -State $fakeState -ProofPath 'self-test' -FileMap $files -CandidateShas $candidateShas -CandidateLabel 'candidate3-self-test-guards' -RepoBranch 'self-test'
    Assert-True ([string]$trustedTransaction.status -eq 'backup-complete') 'Stale active copy hid a live transaction status.'

    $overlapRefused = $false
    try {
        Assert-PathTopology -Game (Join-Path $repo 'build\self-test-state\game') -Candidate (Join-Path $repo 'build\self-test-candidate') -State (Join-Path $repo 'build\self-test-state')
    }
    catch { $overlapRefused = $_.Exception.Message -like '*must not overlap*' }
    Assert-True $overlapRefused 'Game-inside-state overlap was accepted.'

    $outside = Join-Path $tempRoot 'outside'
    $junction = Join-Path $fakeCandidate 'self-test-junction'
    New-Item -ItemType Directory -Force -Path $outside | Out-Null
    New-Item -ItemType Junction -Path $junction -Target $outside | Out-Null
    $reparseRefused = $false
    try { [void](Resolve-SafeChildPath -Root $fakeCandidate -Relative 'self-test-junction/escape.bin' -Label 'fixture candidate') }
    catch { $reparseRefused = $_.Exception.Message -like '*reparse point*' }
    Assert-True $reparseRefused 'Candidate junction path was accepted.'
    Remove-Item -LiteralPath $junction -Force

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
            corrupt_backup_refused_before_any_rollback_write = $true
            backup_phase_failure_wrote_no_game_files = $true
            prewrite_failure_preserved_pending_destination = $true
            per_entry_write_journal_recovery_tested = $true
            force_refused_uncertain_non_candidate_file = $true
            stale_and_unknown_force_status_refused = $true
            stale_active_copy_cannot_hide_live_transaction = $true
            manifest_root_and_exact_file_set_validated = $true
            path_overlap_and_reparse_points_refused = $true
            windows_powershell_relative_path_tested = $true
            game_root_executable_identity_tested = $true
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
    Write-Host '  corrupt backup stopped before rollback write: true'
    Write-Host '  pending destination preserved: true'
    Write-Host '  manifest/status/path guards: true'
    Write-Host '  real God of War files written: false'
    Write-Host "  report: $ReportPath"
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
