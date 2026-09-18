param(
    [string]$GameRoot
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$expectedBranch = 'codex/all-collectibles-production-research'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$runtimeTest = Join-Path $PSScriptRoot 'all-ravens-runtime-test.ps1'
$builder = Join-Path $PSScriptRoot 'build-all-ravens-release-candidate.py'
$buildBehaviorTest = Join-Path $PSScriptRoot 'test_all_ravens_build.py'
$luaBehaviorTest = Join-Path $PSScriptRoot 'test_all_ravens_lua.py'
$candidateRoot = Join-Path $repo 'build\v0.10.5-all-ravens-release-candidate\offline\candidate\game-root'
$frozenSourceRoot = Join-Path $repo 'build\v0.10.5-all-ravens-release-candidate\frozen-source\game-root'
$proofRelative = 'archive/all-ravens/all-ravens-release-candidate-offline.json'
$proofPath = Join-Path $repo 'archive\all-ravens\all-ravens-release-candidate-offline.json'
$runId = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeRunDir = "archive/field-logs/runtime/all-ravens-working-install-$runId"
$runDir = Join-Path $repo "archive\field-logs\runtime\all-ravens-working-install-$runId"
$transcriptPath = Join-Path $runDir 'run.txt'
$resultPath = Join-Path $runDir 'result.json'
$errorDetailPath = Join-Path $runDir 'error.txt'
$gitStatePath = Join-Path $runDir 'git-state.txt'
$activeBeforePath = Join-Path $runDir 'active-transaction-before.json'
$activeAfterPath = Join-Path $runDir 'active-transaction-after.json'
$proofSnapshotPath = Join-Path $runDir 'candidate-proof-used.json'
$candidateManifestPath = Join-Path $runDir 'candidate-files.json'
$transactionSelfTestPath = Join-Path $PSScriptRoot 'test-all-ravens-transaction.ps1'
$transactionSelfTestReportPath = Join-Path $runDir 'transaction-self-test.json'
$activeManifest = Join-Path $repo 'build\v0.10.5-all-ravens-runtime-test\transaction\active.json'
$mainHudRelative = 'mods/lua/gameart/ui/scripts/hud/mainhud.lua'
$coreSaveRelative = 'mods/lua/gameart/scripts/libraries/core/save.lua'

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

function Assert-PowerShellScriptParses {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "PowerShell script is missing: $Path"
    }

    $tokens = $null
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $Path,
        [ref]$tokens,
        [ref]$parseErrors
    )
    if (@($parseErrors).Count -gt 0) {
        $details = @($parseErrors | ForEach-Object {
            "line $($_.Extent.StartLineNumber): $($_.Message)"
        }) -join ' | '
        throw "PowerShell syntax preflight failed for ${Path}: $details"
    }
}

function Write-GitStateSnapshot {
    param([string]$Phase)
    $lines = @(
        "phase=$Phase"
        "timestamp_utc=$((Get-Date).ToUniversalTime().ToString('o'))"
        "branch=$((& git -C $repo branch --show-current).Trim())"
        "head=$((& git -C $repo rev-parse HEAD).Trim())"
        "status_begin"
    )
    $lines += @(& git -C $repo status --short --branch)
    $lines += @(
        "status_end"
        ""
    )
    Add-Content -LiteralPath $gitStatePath -Value $lines -Encoding UTF8
}

function Copy-RunSnapshot {
    param([string]$Source, [string]$Destination)
    if (Test-Path -LiteralPath $Source -PathType Leaf) {
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    }
}

function Write-CandidateFileManifest {
    if (-not (Test-Path -LiteralPath $candidateRoot -PathType Container)) { return }
    $rows = @()
    foreach ($file in @(Get-ChildItem -LiteralPath $candidateRoot -Recurse -File | Sort-Object FullName)) {
        $relative = [IO.Path]::GetRelativePath($candidateRoot, $file.FullName).Replace('\','/')
        $rows += [ordered]@{
            path = $relative
            bytes = [int64]$file.Length
            sha256 = Get-Sha256 -Path $file.FullName
        }
    }
    $payload = [ordered]@{
        schema = 1
        captured_utc = (Get-Date).ToUniversalTime().ToString('o')
        file_count = @($rows).Count
        files = $rows
    }
    [IO.File]::WriteAllText(
        $candidateManifestPath,
        (($payload | ConvertTo-Json -Depth 8) + [Environment]::NewLine),
        (New-Object Text.UTF8Encoding($false))
    )
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

    $frozenMainHud = Join-Path $frozenSourceRoot $mainHudRelative
    $frozenCoreSave = Join-Path $frozenSourceRoot $coreSaveRelative
    if ($complete -and
        (Test-Path -LiteralPath $frozenMainHud -PathType Leaf) -and
        (Test-Path -LiteralPath $frozenCoreSave -PathType Leaf)) {
        $hudText = [IO.File]::ReadAllText($frozenMainHud)
        $saveText = [IO.File]::ReadAllText($frozenCoreSave)
        if ($hudText.Contains('BEGIN COMPLETIONIST V0.10.5 ALL RAVEN UI STATE RECEIVER')) {
            throw 'Frozen MainHUD source unexpectedly already contains the v0.10.5 Raven receiver.'
        }
        if ($saveText.Contains('BEGIN COMPLETIONIST V0.10.5 RAVEN CHECKPOINT CACHE')) {
            throw 'Frozen core.save source unexpectedly already contains the v0.10.5 Raven checkpoint cache.'
        }
        Write-Host '  frozen source: verified base files + MainHUD + core.save baselines'
        return 'verified-existing-with-ui-and-save-cache-baselines'
    }

    if (-not $complete) {
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
    }
    else {
        Write-Host '  frozen source: preserving verified five-file source root while adding MainHUD baseline'
    }

    $mainHudCandidates = @(
        (Join-Path $ResolvedGameRoot $mainHudRelative),
        (Join-Path $ResolvedGameRoot 'mods\lua_source\gameart\ui\scripts\hud\mainhud.lua')
    )
    $mainHudSource = $null
    foreach ($candidate in $mainHudCandidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $text = [IO.File]::ReadAllText($candidate)
        if (-not $text.Contains('local mainHUD = MainHUD.New("mainHUD", {})')) { continue }
        if ($text.Contains('BEGIN COMPLETIONIST V0.10.5 ALL RAVEN UI STATE RECEIVER')) { continue }
        $mainHudSource = $candidate
        break
    }
    if ($null -eq $mainHudSource) {
        throw 'Could not find an unmodified MainHUD baseline for the Raven UI bridge.'
    }
    $mainHudDestination = Join-Path $frozenSourceRoot $mainHudRelative
    New-Item -ItemType Directory -Force -Path (Split-Path $mainHudDestination -Parent) | Out-Null
    Copy-Item -LiteralPath $mainHudSource -Destination $mainHudDestination -Force
    Write-Host "  frozen source captured: $mainHudRelative SHA256=$(Get-Sha256 -Path $mainHudDestination)"

    $coreSaveCandidates = @(
        (Join-Path $ResolvedGameRoot $coreSaveRelative),
        (Join-Path $ResolvedGameRoot 'mods\lua_source\gameart\scripts\libraries\core\save.lua')
    )
    $coreSaveSource = $null
    foreach ($candidate in $coreSaveCandidates) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        $text = [IO.File]::ReadAllText($candidate)
        if (-not $text.Contains('local object_savestate')) { continue }
        if (-not $text.Contains('local Restore = function(savestate)')) { continue }
        if ($text.Contains('BEGIN COMPLETIONIST V0.10.5 RAVEN CHECKPOINT CACHE')) { continue }
        $coreSaveSource = $candidate
        break
    }
    if ($null -eq $coreSaveSource) {
        throw 'Could not find an unmodified core.save baseline for the Raven checkpoint cache.'
    }
    $coreSaveDestination = Join-Path $frozenSourceRoot $coreSaveRelative
    New-Item -ItemType Directory -Force -Path (Split-Path $coreSaveDestination -Parent) | Out-Null
    Copy-Item -LiteralPath $coreSaveSource -Destination $coreSaveDestination -Force
    Write-Host "  frozen source captured: $coreSaveRelative SHA256=$(Get-Sha256 -Path $coreSaveDestination)"

    return 'assembled-from-verified-transaction-backups-with-mainhud-and-core-save'
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

function Invoke-PythonBehaviorTest {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Missing Python behavior test: $Path"
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    $py = Get-Command py -ErrorAction SilentlyContinue

    if ($null -ne $python) {
        & $python.Source $Path 2>&1 | Out-Host
    }
    elseif ($null -ne $py) {
        & $py.Source -3 $Path 2>&1 | Out-Host
    }
    else {
        throw 'Python 3 was not found in PATH; it is required for all-Ravens behavior tests.'
    }

    if ($LASTEXITCODE -ne 0) {
        throw "Behavior test failed: $Path (exit code $LASTEXITCODE)"
    }
}

function Save-LegacyTransactionManifest {
    param([object]$Manifest)
    $json = ($Manifest | ConvertTo-Json -Depth 12) + [Environment]::NewLine
    $encoding = New-Object Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($activeManifest, $json, $encoding)
    $transactionManifest = Join-Path ([string]$Manifest.transaction_root) 'manifest.json'
    [IO.File]::WriteAllText($transactionManifest, $json, $encoding)
}

function Restore-LegacyAllRavensTransaction {
    param([object]$Manifest, [string]$ResolvedGameRoot)

    $legacyCount = @($Manifest.entries).Count
    if ($legacyCount -notin @(5,6)) { throw "Legacy rollback requires five or six entries; found $legacyCount." }
    if ([string]$Manifest.status -ne 'installed') { throw "Legacy transaction status is '$($Manifest.status)', not installed." }
    if (([IO.Path]::GetFullPath([string]$Manifest.game_root)) -ne ([IO.Path]::GetFullPath($ResolvedGameRoot))) {
        throw 'Legacy transaction belongs to a different game root.'
    }
    if (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }) {
        throw 'God of War must be closed before legacy all-Ravens rollback.'
    }

    $entries = @($Manifest.entries)
    foreach ($entry in $entries) {
        if ([string]$entry.write_state -ne 'installed') { throw "Legacy entry is not installed: $($entry.name)" }
        $dest = Join-Path $ResolvedGameRoot ([string]$entry.relative)
        if (-not (Test-Path -LiteralPath $dest -PathType Leaf)) { throw "Legacy installed file missing: $($entry.relative)" }
        if ((Get-Sha256 -Path $dest) -ne ([string]$entry.candidate_sha256).ToLowerInvariant()) {
            throw "Legacy installed file changed since install: $($entry.relative)"
        }
        if ([bool]$entry.existed_before) {
            $backup = Join-Path ([string]$Manifest.transaction_root) ([string]$entry.backup_relative)
            if (-not (Test-Path -LiteralPath $backup -PathType Leaf)) { throw "Legacy backup missing: $($entry.relative)" }
            if ((Get-Sha256 -Path $backup) -ne ([string]$entry.before_sha256).ToLowerInvariant()) {
                throw "Legacy backup SHA differs: $($entry.relative)"
            }
        }
    }

    $Manifest.status = 'rolling-back'
    Save-LegacyTransactionManifest -Manifest $Manifest

    $reverse = @($entries)
    [array]::Reverse($reverse)
    foreach ($entry in $reverse) {
        $dest = Join-Path $ResolvedGameRoot ([string]$entry.relative)
        if ([bool]$entry.existed_before) {
            $backup = Join-Path ([string]$Manifest.transaction_root) ([string]$entry.backup_relative)
            New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null
            Copy-Item -LiteralPath $backup -Destination $dest -Force
            if ((Get-Sha256 -Path $dest) -ne ([string]$entry.before_sha256).ToLowerInvariant()) {
                throw "Legacy rollback verification failed: $($entry.relative)"
            }
        }
        else {
            Remove-Item -LiteralPath $dest -Force -ErrorAction Stop
            if (Test-Path -LiteralPath $dest) { throw "Legacy rollback could not remove: $($entry.relative)" }
        }
        $entry.write_state = 'restored'
        Save-LegacyTransactionManifest -Manifest $Manifest
    }

    $Manifest.status = 'rolled-back'
    $Manifest.rolled_back_utc = (Get-Date).ToUniversalTime().ToString('o')
    Save-LegacyTransactionManifest -Manifest $Manifest
    Write-Host "  legacy $legacyCount-file transaction rolled back exactly: $($Manifest.transaction_id)"
}

function Rollback-ExistingAllRavensInstall {
    param([string]$ResolvedGameRoot)

    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) {
        return 'none'
    }

    $active = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    $status = [string]$active.status
    if ($status -in @('rolled-back','rolled-back-after-install-failure')) {
        return $status
    }
    if ($status -ne 'installed') {
        throw "Existing all-Ravens transaction is '$status'. Automatic upgrade only accepts a clean installed or already rolled-back transaction."
    }

    Write-Host "  previous all-Ravens transaction: $($active.transaction_id) ($status)"
    if (@($active.entries).Count -in @(5,6)) {
        Write-Host "  upgrade: restoring legacy exact $(@($active.entries).Count)-file baseline before seven-file checkpoint-cache build"
        Restore-LegacyAllRavensTransaction -Manifest $active -ResolvedGameRoot $ResolvedGameRoot
    }
    else {
        Write-Host '  upgrade: restoring its exact pre-install seven-file baseline before rebuild'
        & $runtimeTest -Mode Rollback -GameRoot $ResolvedGameRoot -PreserveCurrentBaseline
        if ($LASTEXITCODE -ne 0) {
            throw "Existing all-Ravens rollback failed with exit code $LASTEXITCODE."
        }
    }

    $after = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    if ([string]$after.status -ne 'rolled-back') {
        throw "Existing all-Ravens rollback returned unexpected status '$($after.status)'."
    }
    Write-Host '  upgrade rollback: exact previous baseline restored'
    return 'rolled-back'
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
        schema = 4
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
        evidence = [ordered]@{
            transcript = 'run.txt'
            error_detail = $(if ($null -eq $runError) { $null } else { 'error.txt' })
            git_state = 'git-state.txt'
            active_transaction_before = $(if (Test-Path -LiteralPath $activeBeforePath) { 'active-transaction-before.json' } else { $null })
            active_transaction_after = $(if (Test-Path -LiteralPath $activeAfterPath) { 'active-transaction-after.json' } else { $null })
            candidate_proof_used = $(if (Test-Path -LiteralPath $proofSnapshotPath) { 'candidate-proof-used.json' } else { $null })
            candidate_files = $(if (Test-Path -LiteralPath $candidateManifestPath) { 'candidate-files.json' } else { $null })
            transaction_self_test = $(if (Test-Path -LiteralPath $transactionSelfTestReportPath) { 'transaction-self-test.json' } else { $null })
        }
        install_baseline_policy = 'preserve current seven-file game state for rollback'
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

$branch = ''
$initialHead = ''
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
    Write-GitStateSnapshot -Phase 'start'
    Copy-RunSnapshot -Source $activeManifest -Destination $activeBeforePath

    if (-not (Test-Path -LiteralPath $runtimeTest -PathType Leaf)) {
        throw "Missing runtime transaction script: $runtimeTest"
    }
    $branch = Get-CurrentBranch
    if ($branch -ne $expectedBranch) {
        throw "Expected branch '$expectedBranch', got '$branch'."
    }
    Assert-CleanTrackedState
    $initialHead = Get-RepoHead

    Assert-PowerShellScriptParses -Path $runtimeTest
    Assert-PowerShellScriptParses -Path $transactionSelfTestPath
    Write-Host '  PowerShell syntax preflight: passed'

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
    Write-Host '  transaction: guarded seven-file install with pre-write backups'
    Write-Host '  upgrade policy: safely roll back any active prior all-Ravens install before rebuilding'
    Write-Host ''

    $previousRuntimeAction = Rollback-ExistingAllRavensInstall -ResolvedGameRoot $resolvedGameRoot
    if ($previousRuntimeAction -eq 'rolled-back') {
        Assert-CleanTrackedState
    }

    $frozenSourceAction = Ensure-FrozenSourceRoot -ResolvedGameRoot $resolvedGameRoot
    $candidateAction = Ensure-AllRavensCandidate -SourceRoot $frozenSourceRoot
    Write-CandidateFileManifest
    $proofCommit = Publish-CandidateProofIfChanged
    Copy-RunSnapshot -Source $proofPath -Destination $proofSnapshotPath
    Assert-CleanTrackedState

    Write-Host '  behavior tests: all-Ravens offline build contract'
    Invoke-PythonBehaviorTest -Path $buildBehaviorTest
    Write-Host '  behavior tests: Raven Lua lifecycle contract'
    Invoke-PythonBehaviorTest -Path $luaBehaviorTest
    Write-Host '  behavior tests: passed'
    Assert-CleanTrackedState

    Write-Host '  transaction self-test: running against temporary fake game'
    & $transactionSelfTestPath -ReportPath $transactionSelfTestReportPath
    Write-Host '  transaction self-test: passed'
    Assert-CleanTrackedState

    & $runtimeTest -Mode Install -GameRoot $resolvedGameRoot -ConfirmRuntimeTest -PreserveCurrentBaseline
    if ($LASTEXITCODE -ne 0) {
        throw "All-Ravens runtime installer failed with exit code $LASTEXITCODE."
    }

    $outcome = 'installed'
    Write-Host ''
    Write-Host 'COMPLETIONIST_MAP_ALL_RAVENS_READY'
    Write-Host '  The 53-Raven catalogue build is installed.'
    Write-Host '  The exact seven game files present before this run are the rollback baseline.'
    Write-Host '  A Raven killed during this runtime is hidden by its exact native ravenKilled event.'
    Write-Host '  Existing kills are reconstructed from authoritative native Raven state as zones load.'
    Write-Host '  No Completionist cache is written to GoW saves or sidecar files in this recovery build.'
    Write-Host '  Fresh saves still show all 53 Ravens; unloaded old-save regions remain visible until their WAD loads.'
}
catch {
    $runError = $_
    try {
        [IO.File]::WriteAllText(
            $errorDetailPath,
            ($_.Exception.ToString() + [Environment]::NewLine),
            (New-Object Text.UTF8Encoding($false))
        )
    } catch {}
    Write-Host ''
    Write-Host 'COMPLETIONIST_MAP_ALL_RAVENS_FAILED'
    Write-Host "  $($_.Exception.Message)"
}
finally {
    try { Copy-RunSnapshot -Source $activeManifest -Destination $activeAfterPath } catch {}
    try { Copy-RunSnapshot -Source $proofPath -Destination $proofSnapshotPath } catch {}
    try { Write-CandidateFileManifest } catch {}
    try { Write-GitStateSnapshot -Phase 'finish-before-artifact-commit' } catch {}
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
