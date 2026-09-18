param(
    [string]$GameRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$runtimeTest = Join-Path $PSScriptRoot 'all-ravens-runtime-test.ps1'
$builder = Join-Path $PSScriptRoot 'build-all-ravens-release-candidate.py'
$candidateRoot = Join-Path $repo 'build\v0.10.5-all-ravens-release-candidate\offline\candidate\game-root'
$frozenSourceRoot = Join-Path $repo 'build\v0.10.5-all-ravens-release-candidate\frozen-source\game-root'
$proofRelative = 'archive/all-ravens/all-ravens-release-candidate-offline.json'
$proofPath = Join-Path $repo 'archive\all-ravens\all-ravens-release-candidate-offline.json'
$runId = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeRunDir = "archive/field-logs/runtime/all-ravens-working-install-$runId"
$runDir = Join-Path $repo "archive\field-logs\runtime\all-ravens-working-install-$runId"
$transcriptPath = Join-Path $runDir 'run.txt'
$resultPath = Join-Path $runDir 'result.json'

$sourceFiles = [ordered]@{
    'exec/dc/pc_le/mapmaster.dcb' = '1e1d5086815bc8553490bff915fea210a8be4f80ce6c88b418b62d7050690a31'
    'exec/dc/pc_le/mapcoords.dcb' = '36bd16f8f21c6387b556e156055ea02f5c262b30a6c450cc0efa05734efb1a0c'
    'exec/dc/pc_le/wad_r_ui.dcb' = '9a434a29ed2e333362e60ac7f224d26855fc9dc86834aa94504a170854e22f2b'
    'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua' = '16e13b342f3bbe98ac9b87eb34bf0115e6b04340d6e41270f38a557f2ed51493'
    'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua' = '61e6bc8efe1fcb9b2a6e796aa86ce9a5f74fc18e97229aae7cc52b652a565800'
}

function Get-CurrentBranch {
    $branch = (& git -C $repo branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($branch)) {
        throw 'Could not determine the current Git branch.'
    }
    return $branch
}

function Get-RepoHead {
    $head = (& git -C $repo rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $head -notmatch '^[0-9a-fA-F]{40}$') {
        throw 'Could not determine Git HEAD.'
    }
    return $head.ToLowerInvariant()
}

function Get-Sha256 {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Assert-CleanTrackedState {
    & git -C $repo diff --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) {
        throw 'Tracked working-tree changes exist before the all-Ravens run. Commit or revert them first.'
    }

    & git -C $repo diff --cached --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) {
        throw 'Staged changes exist before the all-Ravens run. Commit or unstage them first.'
    }
}

function Test-GodOfWarRootCandidate {
    param([string]$Path)

    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return $false }

    $gowExe = Join-Path $Path 'GoW.exe'
    $godOfWarExe = Join-Path $Path 'GodOfWar.exe'
    $execDir = Join-Path $Path 'exec'

    $hasGowExe = Test-Path -LiteralPath $gowExe -PathType Leaf
    $hasGodOfWarExe = Test-Path -LiteralPath $godOfWarExe -PathType Leaf
    $hasExecDir = Test-Path -LiteralPath $execDir -PathType Container

    return ($hasGowExe -or $hasGodOfWarExe -or $hasExecDir)
}

function Resolve-GodOfWarRoot {
    param([string]$RequestedRoot)

    if (-not [string]::IsNullOrWhiteSpace($RequestedRoot)) {
        $resolved = [System.IO.Path]::GetFullPath($RequestedRoot)
        if (-not (Test-GodOfWarRootCandidate -Path $resolved)) {
            throw "God of War root is not valid: $resolved"
        }
        return $resolved
    }

    $candidates = New-Object System.Collections.Generic.List[string]

    foreach ($root in @(
        'G:\SteamLibrary\steamapps\common\GodOfWar',
        'C:\Program Files (x86)\Steam\steamapps\common\GodOfWar',
        'C:\Program Files\Steam\steamapps\common\GodOfWar'
    )) {
        $candidates.Add($root)
    }

    try {
        $steamPath = (Get-ItemProperty -LiteralPath 'HKCU:\Software\Valve\Steam' -ErrorAction Stop).SteamPath
        if (-not [string]::IsNullOrWhiteSpace([string]$steamPath)) {
            $steamPath = ([string]$steamPath).Replace('/', '\')
            $candidates.Add((Join-Path $steamPath 'steamapps\common\GodOfWar'))

            $vdf = Join-Path $steamPath 'steamapps\libraryfolders.vdf'
            if (Test-Path -LiteralPath $vdf -PathType Leaf) {
                foreach ($line in Get-Content -LiteralPath $vdf) {
                    if ($line -match '^\s*"path"\s+"(.+)"\s*$') {
                        $library = $Matches[1].Replace('\\', '\')
                        $candidates.Add((Join-Path $library 'steamapps\common\GodOfWar'))
                    }
                }
            }
        }
    }
    catch {
        # Registry discovery is optional; fixed/common locations are still checked below.
    }

    foreach ($code in 67..90) {
        $driveLetter = [char]$code
        $drive = "$driveLetter`:"
        $candidates.Add("$drive\SteamLibrary\steamapps\common\GodOfWar")
        $candidates.Add("$drive\Steam\steamapps\common\GodOfWar")
    }

    $matches = @(
        $candidates |
            Select-Object -Unique |
            Where-Object { Test-GodOfWarRootCandidate -Path $_ }
    )

    if ($matches.Count -eq 0) {
        throw 'Could not auto-detect the God of War installation. Re-run this script with -GameRoot <path-to-GodOfWar>.'
    }
    if ($matches.Count -gt 1) {
        throw "Multiple God of War installations were found. Re-run with -GameRoot and choose one: $($matches -join '; ')"
    }
    return [System.IO.Path]::GetFullPath($matches[0])
}

function Get-SiblingResearchRoots {
    $parent = Split-Path $repo -Parent
    $roots = New-Object System.Collections.Generic.List[string]
    $roots.Add($repo)
    if (Test-Path -LiteralPath $parent -PathType Container) {
        foreach ($dir in @(Get-ChildItem -LiteralPath $parent -Directory -ErrorAction SilentlyContinue)) {
            if ($dir.Name -like 'completionist-map-gow2018*') {
                $roots.Add($dir.FullName)
            }
        }
    }
    return @($roots | Select-Object -Unique)
}

function Find-VerifiedFrozenSourceFile {
    param(
        [string]$Relative,
        [string]$ExpectedSha,
        [string]$ResolvedGameRoot
    )

    $candidates = New-Object System.Collections.Generic.List[string]
    $candidates.Add((Join-Path $ResolvedGameRoot $Relative))

    foreach ($researchRoot in @(Get-SiblingResearchRoots)) {
        $transactionBase = Join-Path $researchRoot 'build\v0.10.5-all-ravens-runtime-test\transaction\transactions'
        if (Test-Path -LiteralPath $transactionBase -PathType Container) {
            foreach ($transaction in @(Get-ChildItem -LiteralPath $transactionBase -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending)) {
                $candidates.Add((Join-Path $transaction.FullName ("backup\game-root\" + $Relative.Replace('/', '\'))))
            }
        }
    }

    foreach ($candidate in @($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $actual = Get-Sha256 -Path $candidate
        if ($actual -eq $ExpectedSha.ToLowerInvariant()) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }

    throw "Could not find frozen verified source for $Relative (expected SHA256 $ExpectedSha). Checked current game plus all sibling completionist-map-gow2018 runtime transaction backups."
}

function Ensure-FrozenSourceRoot {
    param([string]$ResolvedGameRoot)

    $complete = Test-Path -LiteralPath $frozenSourceRoot -PathType Container
    if ($complete) {
        foreach ($relative in $sourceFiles.Keys) {
            $path = Join-Path $frozenSourceRoot $relative
            if ((Get-Sha256 -Path $path) -ne ([string]$sourceFiles[$relative]).ToLowerInvariant()) {
                $complete = $false
                break
            }
        }
    }

    if ($complete) {
        Write-Host '  frozen source: existing verified five-file source root'
        return 'verified-existing'
    }

    if (Test-Path -LiteralPath $frozenSourceRoot) {
        Remove-Item -LiteralPath $frozenSourceRoot -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $frozenSourceRoot | Out-Null

    foreach ($relative in $sourceFiles.Keys) {
        $expected = ([string]$sourceFiles[$relative]).ToLowerInvariant()
        $source = Find-VerifiedFrozenSourceFile -Relative $relative -ExpectedSha $expected -ResolvedGameRoot $ResolvedGameRoot
        $destination = Join-Path $frozenSourceRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $destination -Parent) | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force
        $copiedSha = Get-Sha256 -Path $destination
        if ($copiedSha -ne $expected) {
            throw "Frozen source copy SHA mismatch for $relative."
        }
        Write-Host "  frozen source verified: $relative"
    }

    return 'assembled-from-verified-transaction-backups'
}

function Invoke-CandidateBuilder {
    param(
        [string]$SourceRoot,
        [switch]$CheckOnly
    )

    if (-not (Test-Path -LiteralPath $builder -PathType Leaf)) {
        throw "Missing candidate builder: $builder"
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    $py = Get-Command py -ErrorAction SilentlyContinue
    $args = @($builder, '--source-root', $SourceRoot)
    if ($CheckOnly) {
        $args += '--check'
    }

    if ($null -ne $python) {
        & $python.Source @args 2>&1 | Out-Host
    }
    elseif ($null -ne $py) {
        & $py.Source -3 @args 2>&1 | Out-Host
    }
    else {
        throw 'Python 3 was not found in PATH; it is required to rebuild the ignored all-Ravens candidate.'
    }

    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        $mode = if ($CheckOnly) { 'verification' } else { 'build' }
        throw "All-Ravens candidate $mode failed with exit code $exitCode."
    }
}

function Ensure-AllRavensCandidate {
    param([string]$SourceRoot)

    if (Test-Path -LiteralPath $candidateRoot) {
        Remove-Item -LiteralPath $candidateRoot -Recurse -Force
    }

    Write-Host '  candidate: rebuilding deterministically from frozen verified source'
    Invoke-CandidateBuilder -SourceRoot $SourceRoot

    if (-not (Test-Path -LiteralPath $candidateRoot -PathType Container)) {
        throw "Candidate builder completed but the candidate root is still missing: $candidateRoot"
    }

    Invoke-CandidateBuilder -SourceRoot $SourceRoot -CheckOnly
    Write-Host '  candidate: rebuilt and deterministic rebuild verified'
    return 'rebuilt-from-frozen-source'
}

function Publish-CandidateProofIfChanged {
    & git -C $repo diff --quiet --ignore-submodules -- $proofRelative
    if ($LASTEXITCODE -eq 0) {
        Write-Host '  candidate proof: tracked proof already matches rebuilt candidate'
        return $null
    }

    if (-not (Test-Path -LiteralPath $proofPath -PathType Leaf)) {
        throw "Candidate build changed proof state but proof file is missing: $proofPath"
    }

    & git -C $repo add -- $proofRelative 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage refreshed all-Ravens candidate proof.' }

    & git -C $repo commit -m 'build(v0.10.5): refresh all-ravens candidate proof' -- $proofRelative 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Could not commit refreshed all-Ravens candidate proof.' }

    $commit = Get-RepoHead
    & git -C $repo push origin $expectedBranch 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Candidate proof committed locally as $commit but push failed." }

    Write-Host "  candidate proof commit: $commit"
    return $commit
}

function Write-RunResult {
    param(
        [string]$Outcome,
        [string]$Branch,
        [string]$InitialHead,
        [string]$ResolvedGameRoot,
        [string]$FrozenSourceAction,
        [string]$CandidateAction,
        [string]$ProofCommit,
        [string]$ErrorMessage
    )

    $result = [ordered]@{
        schema = 3
        run_id = $runId
        finished_utc = (Get-Date).ToUniversalTime().ToString('o')
        outcome = $Outcome
        branch = $Branch
        repo_head_at_start = $InitialHead
        game_root = $ResolvedGameRoot
        frozen_source_action = $FrozenSourceAction
        frozen_source_root = $frozenSourceRoot
        candidate_action = $CandidateAction
        candidate_root = $candidateRoot
        candidate_proof_commit = $ProofCommit
        install_baseline_policy = 'preserve current five-file game state for rollback'
        catalogue_markers = 53
        unknown_raven_state_visible = $true
        live_native_ravenKilled_events = $true
        persisted_raven_bootstrap = 'read-only pickle GameObject WAD/object join on map open'
        persisted_unmatched_policy = 'visible'
        installer_writes_save_or_progression = $false
        error = $ErrorMessage
    }

    $json = $result | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText(
        $resultPath,
        $json + [Environment]::NewLine,
        (New-Object System.Text.UTF8Encoding($false))
    )
}

function Publish-RunArtifacts {
    param([string]$Outcome)

    & git -C $repo add -- $relativeRunDir 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "Could not stage run artifacts: $relativeRunDir"
    }

    & git -C $repo diff --cached --quiet --ignore-submodules -- $relativeRunDir
    if ($LASTEXITCODE -eq 0) {
        Write-Host '  GitHub artifact publish: no run-artifact changes to commit'
        return (Get-RepoHead)
    }

    $message = "field: record all-Ravens install $Outcome $runId"
    & git -C $repo commit -m $message -- $relativeRunDir 2>&1 | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not commit the run artifacts.'
    }

    $commit = Get-RepoHead
    $pushed = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        & git -C $repo push origin $expectedBranch 2>&1 | Out-Host
        if ($LASTEXITCODE -eq 0) {
            $pushed = $true
            break
        }
        Start-Sleep -Seconds (2 * $attempt)
    }

    if (-not $pushed) {
        throw "Run artifacts were committed locally as $commit but could not be pushed after 3 attempts."
    }

    Write-Host "  GitHub artifact commit: $commit"
    return $commit
}

if (-not (Test-Path -LiteralPath $runtimeTest -PathType Leaf)) {
    throw "Missing runtime transaction script: $runtimeTest"
}

$branch = Get-CurrentBranch
if ($branch -ne $expectedBranch) {
    throw "Expected branch '$expectedBranch', got '$branch'."
}

Assert-CleanTrackedState
$initialHead = Get-RepoHead
$resolvedGameRoot = $null
$frozenSourceAction = 'not-attempted'
$candidateAction = 'not-attempted'
$proofCommit = $null
$outcome = 'failed'
$runError = $null
$transcriptStarted = $false
$artifactCommit = $null
$publishError = $null

New-Item -ItemType Directory -Force -Path $runDir | Out-Null

try {
    Start-Transcript -LiteralPath $transcriptPath -Force | Out-Null
    $transcriptStarted = $true

    $resolvedGameRoot = Resolve-GodOfWarRoot -RequestedRoot $GameRoot

    Write-Host 'COMPLETIONIST_MAP_ALL_RAVENS_INSTALL'
    Write-Host "  run id: $runId"
    Write-Host "  branch: $branch"
    Write-Host "  repo head at start: $initialHead"
    Write-Host "  game root: $resolvedGameRoot"
    Write-Host '  catalogue markers: 53'
    Write-Host '  unknown Raven state: visible'
    Write-Host '  live native ravenKilled events: enabled'
    Write-Host '  old-save bootstrap: read-only persisted GameObject scan on map open'
    Write-Host '  persisted identity: exact unique WAD + GameObject name'
    Write-Host '  save/progression writes by installer: none'
    Write-Host '  candidate source: frozen SHA-verified transaction backups'
    Write-Host '  pre-install game state: preserved as rollback baseline'
    Write-Host '  transaction: guarded five-file install with pre-write backups'
    Write-Host ''

    $frozenSourceAction = Ensure-FrozenSourceRoot -ResolvedGameRoot $resolvedGameRoot
    $candidateAction = Ensure-AllRavensCandidate -SourceRoot $frozenSourceRoot
    $proofCommit = Publish-CandidateProofIfChanged
    Assert-CleanTrackedState

    & $runtimeTest -Mode Install -GameRoot $resolvedGameRoot -ConfirmRuntimeTest -PreserveCurrentBaseline
    if ($LASTEXITCODE -ne 0) {
        throw "All-Ravens runtime installer failed with exit code $LASTEXITCODE."
    }

    $outcome = 'installed'
    Write-Host ''
    Write-Host 'COMPLETIONIST_MAP_ALL_RAVENS_READY'
    Write-Host '  The 53-Raven catalogue build is installed.'
    Write-Host '  The exact five game files present before this run are the rollback baseline.'
    Write-Host '  A Raven killed during this runtime is hidden by its exact native ravenKilled event.'
    Write-Host '  Existing kills are reconstructed read-only from persisted Raven GameObjects when the map opens.'
    Write-Host '  Fresh saves still show all 53 Ravens; unmatched/ambiguous state remains visible by design.'
}
catch {
    $runError = $_
    Write-Host ''
    Write-Host 'COMPLETIONIST_MAP_ALL_RAVENS_FAILED'
    Write-Host "  $($_.Exception.Message)"
}
finally {
    if ($transcriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
    }
}

$errorMessage = if ($null -eq $runError) { $null } else { [string]$runError.Exception.Message }
Write-RunResult `
    -Outcome $outcome `
    -Branch $branch `
    -InitialHead $initialHead `
    -ResolvedGameRoot $resolvedGameRoot `
    -FrozenSourceAction $frozenSourceAction `
    -CandidateAction $candidateAction `
    -ProofCommit $proofCommit `
    -ErrorMessage $errorMessage

try {
    $artifactCommit = Publish-RunArtifacts -Outcome $outcome
}
catch {
    $publishError = $_
    Write-Host "GitHub auto-publish failed: $($_.Exception.Message)"
}

if ($null -ne $runError) {
    if ($null -ne $artifactCommit) {
        throw "All-Ravens install failed; its transcript/result were pushed in commit $artifactCommit. Error: $errorMessage"
    }
    if ($null -ne $publishError) {
        throw "All-Ravens install failed, and its automatic GitHub publish also failed. Install error: $errorMessage | Publish error: $($publishError.Exception.Message)"
    }
    throw "All-Ravens install failed: $errorMessage"
}

if ($null -ne $publishError) {
    throw "The all-Ravens install completed, but automatic GitHub publishing failed: $($publishError.Exception.Message)"
}

Write-Host "COMPLETIONIST_MAP_ALL_RAVENS_RESULT_PUSHED $artifactCommit"
