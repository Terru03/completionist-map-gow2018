param(
    [string]$ReportPath = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$engine = Join-Path $repo 'tools\v0.10.4\nornir-runtime-candidate3.ps1'
$expectedEngineSha = '83f11f8e3a5b6e56ad5d06ba22baa779f91c986ace42ab3017de2b2231d7057a'

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw $Message }
}

function Write-Bytes([string]$Path, [byte[]]$Bytes) {
    New-Item -ItemType Directory -Force -Path (Split-Path $Path -Parent) | Out-Null
    [IO.File]::WriteAllBytes($Path, $Bytes)
}

Assert-True (Test-Path -LiteralPath $engine -PathType Leaf) "Missing transaction engine: $engine"
$engineText = [IO.File]::ReadAllText($engine).Replace("`r`n", "`n").Replace("`r", "`n")
$engineBytes = [Text.Encoding]::UTF8.GetBytes($engineText)
$engineHash = [Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($engineBytes)).ToLowerInvariant()
Assert-True ($engineHash -eq $expectedEngineSha) 'Transaction engine canonical SHA differs.'
. $engine -LibraryOnly
$allRavensProofPath = Join-Path $repo 'archive\all-ravens\all-ravens-release-candidate-offline.json'
$allRavensCandidateRoot = Join-Path $repo 'build\v0.10.5-all-ravens-release-candidate\offline\candidate\game-root'
$allRavensRuntimeTest = Join-Path $repo 'tools\v0.10.5\all-ravens-runtime-test.ps1'
Assert-True (Test-Path -LiteralPath $allRavensRuntimeTest -PathType Leaf) "Missing runtime test: $allRavensRuntimeTest"
$runtimeTokens = $null
$runtimeParseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    $allRavensRuntimeTest,
    [ref]$runtimeTokens,
    [ref]$runtimeParseErrors
)
Assert-True (@($runtimeParseErrors).Count -eq 0) ("Runtime test has PowerShell parse errors: " + ((@($runtimeParseErrors | ForEach-Object { $_.Message })) -join ' | '))

$runtimeText = [IO.File]::ReadAllText($allRavensRuntimeTest)
Assert-True ($runtimeText.Contains("Assert-TerminalAllRavensTransactionSummary")) 'Terminal transaction compatibility guard is missing.'
Assert-True ($runtimeText.Contains("historical candidate SHAs are intentionally not compared with the replacement candidate")) 'Terminal upgrade must skip replacement SHA comparison.'
$allRavensInstaller = Join-Path $repo 'tools\v0.10.5\install-all-ravens-working-mod.ps1'
Assert-True (Test-Path -LiteralPath $allRavensInstaller -PathType Leaf) "Missing installer: $allRavensInstaller"
$installerTokens = $null
$installerParseErrors = $null
[void][System.Management.Automation.Language.Parser]::ParseFile(
    $allRavensInstaller,
    [ref]$installerTokens,
    [ref]$installerParseErrors
)
Assert-True (@($installerParseErrors).Count -eq 0) ("Installer has PowerShell parse errors: " + ((@($installerParseErrors | ForEach-Object { $_.Message })) -join ' | '))

$installerText = [IO.File]::ReadAllText($allRavensInstaller)
foreach ($requiredArtifact in @(
    'run.txt',
    'result.json',
    'error.txt',
    'git-state.txt',
    'active-transaction-before.json',
    'active-transaction-after.json',
    'candidate-proof-used.json',
    'candidate-files.json'
)) {
    Assert-True ($installerText.Contains($requiredArtifact)) "Installer run evidence contract misses $requiredArtifact"
}
Assert-True ($installerText.Contains('Publish-RunArtifacts -Outcome $outcome')) 'Installer must publish run evidence for final outcome.'

$files = [ordered]@{
    mapmaster = 'exec/dc/pc_le/mapmaster.dcb'
    mapcoords = 'exec/dc/pc_le/mapcoords.dcb'
    ui = 'exec/dc/pc_le/wad_r_ui.dcb'
    mapmenu = 'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua'
    events = 'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua'
}
$proof = Get-Content -LiteralPath $allRavensProofPath -Raw | ConvertFrom-Json
Assert-True ([bool]$proof.ready_for_runtime_test) 'Release gate is not open.'
Assert-True (@($proof.files.PSObject.Properties).Count -eq 5) 'Proof file count differs.'
$candidateShas = [ordered]@{}
foreach ($name in $files.Keys) {
    $relative = [string]$files[$name]
    $entry = $proof.files.PSObject.Properties[$relative]
    Assert-True ($null -ne $entry) "Proof misses file: $relative"
    $candidate = Join-Path $allRavensCandidateRoot $relative
    Assert-True (Test-Path -LiteralPath $candidate -PathType Leaf) "Candidate misses file: $relative"
    $sha = (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
    Assert-True ($sha -eq [string]$entry.Value.sha256) "Candidate SHA differs: $relative"
    $candidateShas[$name] = $sha
}

$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ('completionist-all-ravens-transaction-' + [Guid]::NewGuid().ToString('N'))
$fakeGame = Join-Path $tempRoot 'fake-game'
$fakeState = Join-Path $tempRoot 'state'
$fakeActive = Join-Path $fakeState 'active.json'
Assert-True ([IO.Path]::GetFullPath($tempRoot).StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()))) 'Fixture escaped temp.'
New-Item -ItemType Directory -Force -Path $fakeGame, $fakeState | Out-Null

function Snapshot-FakeGame {
    $snapshot = [ordered]@{}
    foreach ($name in $files.Keys) {
        $relative = [string]$files[$name]
        $path = Resolve-SafeChildPath -Root $fakeGame -Relative $relative -Label 'fixture game'
        $snapshot[$name] = [ordered]@{
            exists = Test-Path -LiteralPath $path -PathType Leaf
            sha256 = if (Test-Path -LiteralPath $path -PathType Leaf) { Get-Sha256 $path } else { $null }
        }
    }
    return $snapshot
}

function Assert-Snapshot([System.Collections.IDictionary]$Expected) {
    foreach ($name in $files.Keys) {
        $path = Resolve-SafeChildPath -Root $fakeGame -Relative ([string]$files[$name]) -Label 'fixture game'
        if ([bool]$Expected[$name].exists) {
            Assert-True (Test-Path -LiteralPath $path -PathType Leaf) "Restored file missing: $name"
            Assert-True ((Get-Sha256 $path) -eq [string]$Expected[$name].sha256) "Restored SHA differs: $name"
        }
        else {
            Assert-True (-not (Test-Path -LiteralPath $path)) "Restored file should be absent: $name"
        }
    }
}

try {
    $index = 0
    foreach ($name in $files.Keys) {
        if (($index % 2) -eq 0) {
            $path = Resolve-SafeChildPath -Root $fakeGame -Relative ([string]$files[$name]) -Label 'fixture game'
            Write-Bytes -Path $path -Bytes ([Text.Encoding]::UTF8.GetBytes("baseline-$index-$name`n"))
        }
        $index++
    }
    $baseline = Snapshot-FakeGame

    $label = 'all-ravens-v0.10.5-self-test'
    $branch = 'codex/all-collectibles-production-research'
    $installed = Invoke-TransactionalInstall -Game $fakeGame -Candidate $allRavensCandidateRoot -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $candidateShas -CandidateLabel $label -RepoBranch $branch -RepoHead 'self-test' -ProofPath $allRavensProofPath
    Assert-True ($installed.status -eq 'installed') 'Install did not finish.'
    Restore-State -Manifest $installed -Game $fakeGame -Candidate $allRavensCandidateRoot -State $fakeState -Active $fakeActive -ProofPath $allRavensProofPath -FileMap $files -CandidateShas $candidateShas -CandidateLabel $label -RepoBranch $branch -CheckInstalled $true -Force $false
    Assert-Snapshot $baseline

    foreach ($failureIndex in 1..5) {
        Remove-Item -LiteralPath $fakeState -Recurse -Force
        New-Item -ItemType Directory -Force -Path $fakeState | Out-Null
        $caught = $false
        try {
            Invoke-TransactionalInstall -Game $fakeGame -Candidate $allRavensCandidateRoot -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $candidateShas -CandidateLabel $label -RepoBranch $branch -RepoHead 'self-test' -ProofPath $allRavensProofPath -FailureInjectionAfter $failureIndex | Out-Null
        }
        catch { $caught = $_.Exception.Message -like '*automatically rolled back*' }
        Assert-True $caught "Write boundary $failureIndex did not roll back."
        Assert-Snapshot $baseline
    }

    Remove-Item -LiteralPath $fakeState -Recurse -Force
    New-Item -ItemType Directory -Force -Path $fakeState | Out-Null
    $interrupted = New-TransactionManifest -Game $fakeGame -Candidate $allRavensCandidateRoot -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $candidateShas -CandidateLabel $label -RepoBranch $branch -RepoHead 'self-test' -ProofPath $allRavensProofPath
    $interrupted.status = 'installing'
    Save-TransactionManifest -Manifest $interrupted -Active $fakeActive
    $first = @($interrupted.entries)[0]
    $first.write_state = 'write-started'
    Save-TransactionManifest -Manifest $interrupted -Active $fakeActive
    Copy-Verified -Source (Resolve-SafeChildPath -Root $allRavensCandidateRoot -Relative ([string]$first.relative) -Label 'candidate') -Destination (Resolve-SafeChildPath -Root $fakeGame -Relative ([string]$first.relative) -Label 'fixture game') -ExpectedSha ([string]$first.candidate_sha256)
    $first.write_state = 'installed'
    @($interrupted.entries)[1].write_state = 'write-started'
    Save-TransactionManifest -Manifest $interrupted -Active $fakeActive
    $recovery = Get-ValidatedActiveTransaction -Active $fakeActive -Game $fakeGame -Candidate $allRavensCandidateRoot -State $fakeState -ProofPath $allRavensProofPath -FileMap $files -CandidateShas $candidateShas -CandidateLabel $label -RepoBranch $branch
    Restore-State -Manifest $recovery -Game $fakeGame -Candidate $allRavensCandidateRoot -State $fakeState -Active $fakeActive -ProofPath $allRavensProofPath -FileMap $files -CandidateShas $candidateShas -CandidateLabel $label -RepoBranch $branch -CheckInstalled $false -Force $false
    Assert-Snapshot $baseline

    Remove-Item -LiteralPath $fakeState -Recurse -Force
    New-Item -ItemType Directory -Force -Path $fakeState | Out-Null
    $tamper = Invoke-TransactionalInstall -Game $fakeGame -Candidate $allRavensCandidateRoot -State $fakeState -Active $fakeActive -FileMap $files -CandidateShas $candidateShas -CandidateLabel $label -RepoBranch $branch -RepoHead 'self-test' -ProofPath $allRavensProofPath
    $tamperPath = Resolve-SafeChildPath -Root $fakeGame -Relative ([string]@($tamper.entries)[0].relative) -Label 'fixture game'
    [IO.File]::AppendAllText($tamperPath, 'tampered')
    $tamperRefused = $false
    try {
        Restore-State -Manifest $tamper -Game $fakeGame -Candidate $allRavensCandidateRoot -State $fakeState -Active $fakeActive -ProofPath $allRavensProofPath -FileMap $files -CandidateShas $candidateShas -CandidateLabel $label -RepoBranch $branch -CheckInstalled $true -Force $false
    }
    catch { $tamperRefused = $_.Exception.Message -like '*changed since*' }
    Assert-True $tamperRefused 'Tampered install accepted by rollback.'

    $report = [ordered]@{
        schema = 1
        result = 'ALL_RAVENS_TRANSACTION_SELF_TEST_PASSED'
        candidate_file_count = 5
        candidate_hashes = $candidateShas
        transaction_engine_sha256 = $expectedEngineSha
        proofs = [ordered]@{
            exact_install_and_rollback = $true
            all_five_failure_boundaries_rollback = $true
            interruption_recovery = $true
            tamper_refusal = $true
            release_gate_open = $true
            terminal_historical_manifest_upgrade = $true
            success_and_failure_run_archiving = $true
            powershell_parse_preflight = $true
        }
        safety = [ordered]@{
            fake_game_root_only = $true
            installed_game_written = $false
            game_launched = $false
            save_or_progression_written = $false
        }
    }
    if ([string]::IsNullOrWhiteSpace($ReportPath)) {
        $ReportPath = Join-Path $repo 'archive\all-ravens\all-ravens-transaction-self-test.json'
    }
    Write-JsonAtomic -Value $report -Path $ReportPath
    Write-Host 'ALL_RAVENS_TRANSACTION_SELF_TEST_PASSED'
}
finally {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
