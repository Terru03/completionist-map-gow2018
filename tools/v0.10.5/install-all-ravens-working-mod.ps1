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
$runId = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeRunDir = "archive/field-logs/runtime/all-ravens-working-install-$runId"
$runDir = Join-Path $repo "archive\field-logs\runtime\all-ravens-working-install-$runId"
$transcriptPath = Join-Path $runDir 'run.txt'
$resultPath = Join-Path $runDir 'result.json'

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

function Invoke-CandidateBuilder {
    param(
        [string]$ResolvedGameRoot,
        [switch]$CheckOnly
    )

    if (-not (Test-Path -LiteralPath $builder -PathType Leaf)) {
        throw "Missing candidate builder: $builder"
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    $py = Get-Command py -ErrorAction SilentlyContinue
    $args = @($builder, '--source-root', $ResolvedGameRoot)
    if ($CheckOnly) {
        $args += '--check'
    }

    if ($null -ne $python) {
        & $python.Source @args
    }
    elseif ($null -ne $py) {
        & $py.Source -3 @args
    }
    else {
        throw 'Python 3 was not found in PATH; it is required to rebuild the ignored all-Ravens candidate.'
    }

    if ($LASTEXITCODE -ne 0) {
        $mode = if ($CheckOnly) { 'verification' } else { 'build' }
        throw "All-Ravens candidate $mode failed with exit code $LASTEXITCODE."
    }
}

function Ensure-AllRavensCandidate {
    param([string]$ResolvedGameRoot)

    $action = 'verified-existing'
    if (-not (Test-Path -LiteralPath $candidateRoot -PathType Container)) {
        Write-Host '  candidate root: missing; rebuilding deterministically'
        Invoke-CandidateBuilder -ResolvedGameRoot $ResolvedGameRoot
        $action = 'rebuilt'
    }
    else {
        Write-Host '  candidate root: present; verifying deterministic rebuild'
    }

    if (-not (Test-Path -LiteralPath $candidateRoot -PathType Container)) {
        throw "Candidate builder completed but the candidate root is still missing: $candidateRoot"
    }

    Invoke-CandidateBuilder -ResolvedGameRoot $ResolvedGameRoot -CheckOnly
    Write-Host "  candidate: $action and verified"
    return $action
}

function Write-RunResult {
    param(
        [string]$Outcome,
        [string]$Branch,
        [string]$HeadBefore,
        [string]$ResolvedGameRoot,
        [string]$CandidateAction,
        [string]$ErrorMessage
    )

    $result = [ordered]@{
        schema = 2
        run_id = $runId
        finished_utc = (Get-Date).ToUniversalTime().ToString('o')
        outcome = $Outcome
        branch = $Branch
        repo_head_before = $HeadBefore
        game_root = $ResolvedGameRoot
        candidate_action = $CandidateAction
        candidate_root = $candidateRoot
        catalogue_markers = 53
        unknown_raven_state_visible = $true
        live_native_ravenKilled_events = $true
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

    & git -C $repo add -- $relativeRunDir
    if ($LASTEXITCODE -ne 0) {
        throw "Could not stage run artifacts: $relativeRunDir"
    }

    & git -C $repo diff --cached --quiet --ignore-submodules -- $relativeRunDir
    if ($LASTEXITCODE -eq 0) {
        Write-Host '  GitHub artifact publish: no run-artifact changes to commit'
        return (Get-RepoHead)
    }

    $message = "field: record all-Ravens install $Outcome $runId"
    & git -C $repo commit -m $message -- $relativeRunDir
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not commit the run artifacts.'
    }

    $commit = Get-RepoHead
    $pushed = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        & git -C $repo push origin $expectedBranch
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
$headBefore = Get-RepoHead
$resolvedGameRoot = $null
$candidateAction = 'not-attempted'
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
    Write-Host "  repo head: $headBefore"
    Write-Host "  game root: $resolvedGameRoot"
    Write-Host '  catalogue markers: 53'
    Write-Host '  unknown Raven state: visible'
    Write-Host '  live native ravenKilled events: enabled'
    Write-Host '  save/progression writes by installer: none'
    Write-Host '  candidate: auto-build/verify before install'
    Write-Host '  transaction: guarded five-file install with pre-write backups'
    Write-Host ''

    $candidateAction = Ensure-AllRavensCandidate -ResolvedGameRoot $resolvedGameRoot

    & $runtimeTest -Mode Install -GameRoot $resolvedGameRoot -ConfirmRuntimeTest
    if ($LASTEXITCODE -ne 0) {
        throw "All-Ravens runtime installer failed with exit code $LASTEXITCODE."
    }

    $outcome = 'installed'
    Write-Host ''
    Write-Host 'COMPLETIONIST_MAP_ALL_RAVENS_READY'
    Write-Host '  The 53-Raven catalogue build is installed.'
    Write-Host '  A Raven killed during this runtime is hidden by its exact native ravenKilled event.'
    Write-Host '  Existing kills from an old save are not yet reconstructed until the persisted-kill bootstrap is completed.'
    Write-Host '  Fresh/unknown Raven state remains visible by design.'
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
    -HeadBefore $headBefore `
    -ResolvedGameRoot $resolvedGameRoot `
    -CandidateAction $candidateAction `
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
