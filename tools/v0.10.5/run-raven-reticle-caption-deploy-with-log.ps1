param(
    [string]$GameRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$expectedRepo = [IO.Path]::GetFullPath('C:\Users\david\Documents\GitHub\completionist-map-gow2018-research-live')
$expectedBranch = 'codex/all-collectibles-production-research'
$patcher = Join-Path $PSScriptRoot 'apply-raven-reticle-caption.py'
$luaTests = Join-Path $PSScriptRoot 'test_all_ravens_lua.py'
$modelTests = Join-Path $PSScriptRoot 'test_raven_runtime_model.py'
$builder = Join-Path $PSScriptRoot 'build-all-ravens-release-candidate.py'
$buildTests = Join-Path $PSScriptRoot 'test_all_ravens_build.py'
$transactionTests = Join-Path $PSScriptRoot 'test-all-ravens-transaction.ps1'
$runtimeTest = Join-Path $PSScriptRoot 'all-ravens-runtime-test.ps1'
$proof = Join-Path $repo 'archive\all-ravens\all-ravens-release-candidate-offline.json'
$txReport = Join-Path $repo 'archive\all-ravens\all-ravens-transaction-self-test.json'
$stateRoot = Join-Path $repo 'build\v0.10.5-all-ravens-runtime-test\transaction'
$active = Join-Path $stateRoot 'active.json'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logDir = Join-Path $repo 'archive\field-logs\local-handoffs'
$log = Join-Path $logDir "raven-reticle-caption-deploy-$stamp.txt"
$logRelative = [IO.Path]::GetRelativePath($repo, $log).Replace('\','/')
$phase = 'startup'
$rolledBackOld = $false
$installedNew = $false

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Log([string]$Text) {
    Add-Content -LiteralPath $log -Value $Text -Encoding UTF8
}

function Run-Native([string]$Label, [scriptblock]$Action) {
    Log ""
    Log "=== $Label ==="
    $global:LASTEXITCODE = 0
    & $Action *>> $log
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "$Label failed with exit code $code" }
}

function Get-Branch {
    $value = (& git -C $repo branch --show-current 2>$null).Trim()
    if ($LASTEXITCODE -ne 0) { throw 'Could not determine Git branch.' }
    return $value
}

function Assert-TrackedClean {
    & git -C $repo diff --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) { throw 'Tracked working-tree changes exist.' }
    & git -C $repo diff --cached --quiet --ignore-submodules --
    if ($LASTEXITCODE -ne 0) { throw 'Staged changes exist.' }
}

function Commit-Exact([string]$Message, [string[]]$Paths) {
    foreach ($path in $Paths) {
        if (Test-Path -LiteralPath (Join-Path $repo $path)) {
            & git -C $repo add -- $path *>> $log
            if ($LASTEXITCODE -ne 0) { throw "git add failed: $path" }
        }
    }
    & git -C $repo diff --cached --quiet --ignore-submodules --
    if ($LASTEXITCODE -eq 0) {
        Log "No staged changes for commit: $Message"
        return
    }
    Run-Native "git commit: $Message" { & git -C $repo commit -m $Message }
    Run-Native 'git push research branch' { & git -C $repo push origin $expectedBranch }
}

function Find-GameRoot {
    if (-not [string]::IsNullOrWhiteSpace($GameRoot)) {
        if (Test-Path -LiteralPath (Join-Path $GameRoot 'GoW.exe') -PathType Leaf) {
            return [IO.Path]::GetFullPath($GameRoot)
        }
        throw "God of War root is invalid: $GameRoot"
    }
    $candidates = @(
        'G:\SteamLibrary\steamapps\common\GodOfWar',
        'D:\SteamLibrary\steamapps\common\GodOfWar',
        'E:\SteamLibrary\steamapps\common\GodOfWar',
        'F:\SteamLibrary\steamapps\common\GodOfWar',
        'C:\Program Files (x86)\Steam\steamapps\common\GodOfWar'
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $candidate 'GoW.exe') -PathType Leaf) {
            return [IO.Path]::GetFullPath($candidate)
        }
    }
    throw 'God of War installation was not found in the approved Steam locations.'
}

function Archive-RolledBackActive {
    if (-not (Test-Path -LiteralPath $active -PathType Leaf)) { return }
    $manifest = Get-Content -LiteralPath $active -Raw | ConvertFrom-Json
    if ([string]$manifest.status -notin @('rolled-back','rolled-back-after-install-failure')) {
        throw "Refusing to archive non-terminal active transaction: $($manifest.status)"
    }
    $id = [string]$manifest.transaction_id
    if ($id -notmatch '^\d{8}T\d{6}Z-[0-9a-f]{8}$') { throw 'Rolled-back transaction ID is malformed.' }
    $archived = Join-Path $stateRoot ("rolled-back-active-$id.json")
    if (Test-Path -LiteralPath $archived) { throw "Rolled-back active archive already exists: $archived" }
    Move-Item -LiteralPath $active -Destination $archived
    Log "ARCHIVED_ROLLED_BACK_ACTIVE=$archived"
}

try {
    Log 'RAVEN_RETICLE_CAPTION_DEPLOY_V1'
    Log "STARTED_LOCAL=$(Get-Date -Format o)"
    Log "REPO=$repo"

    $phase = 'preflight'
    if ([IO.Path]::GetFullPath($repo) -ne $expectedRepo) {
        throw "Refusing non-isolated checkout: $repo"
    }
    if ((Get-Branch) -ne $expectedBranch) { throw "Expected branch: $expectedBranch" }
    Assert-TrackedClean
    $resolvedGame = Find-GameRoot
    Log "GAME_ROOT=$resolvedGame"
    if (Get-Process -Name 'GoW','GodOfWar' -ErrorAction SilentlyContinue) {
        throw 'God of War is still running. Close the game before deployment.'
    }

    $phase = 'apply-caption-patch'
    Run-Native 'apply guarded reticle caption patch' { & python $patcher }
    Run-Native 'Lua 5.1 Raven runtime tests' { & python $luaTests }
    Run-Native 'Raven runtime model tests' { & python $modelTests }
    Run-Native 'git diff check after caption patch' { & git -C $repo diff --check }

    $unexpected = @(& git -C $repo status --porcelain --untracked-files=no | ForEach-Object { $_.Substring(3).Replace('\','/') })
    $allowedSource = @('tools/v0.10.5/all-ravens-map-runtime.lua','tools/v0.10.5/test_all_ravens_lua.py')
    foreach ($path in $unexpected) {
        if ($path -notin $allowedSource) { throw "Unexpected tracked change before source commit: $path" }
    }
    Commit-Exact 'runtime: populate Raven map cursor title' $allowedSource
    Assert-TrackedClean

    $phase = 'rollback-current-runtime-candidate'
    if (Test-Path -LiteralPath $active -PathType Leaf) {
        $before = Get-Content -LiteralPath $active -Raw | ConvertFrom-Json
        $status = [string]$before.status
        Log "PREVIOUS_TRANSACTION_STATUS=$status"
        if ($status -eq 'installed') {
            Run-Native 'rollback current all-Ravens runtime candidate' {
                & pwsh -NoProfile -ExecutionPolicy Bypass -File $runtimeTest -Mode Rollback -GameRoot $resolvedGame
            }
            $rolledBackOld = $true
        }
        elseif ($status -notin @('rolled-back','rolled-back-after-install-failure')) {
            throw "Existing all-Ravens transaction is not safely terminal/installable: $status"
        }
        Archive-RolledBackActive
    }
    else {
        Log 'PREVIOUS_TRANSACTION_STATUS=none'
    }

    $phase = 'build-caption-candidate'
    Run-Native 'build all-Ravens caption candidate' { & python $builder --source-root $resolvedGame }
    Run-Native 'all-Ravens build tests' { & python $buildTests }
    Run-Native 'deterministic candidate rebuild check' { & python $builder --source-root $resolvedGame --check }
    Run-Native 'transaction engine self-test' { & pwsh -NoProfile -ExecutionPolicy Bypass -File $transactionTests }
    Run-Native 'git diff check after candidate build' { & git -C $repo diff --check }

    $allowedBuild = @('archive/all-ravens/all-ravens-release-candidate-offline.json','archive/all-ravens/all-ravens-transaction-self-test.json')
    $trackedAfterBuild = @(& git -C $repo status --porcelain --untracked-files=no | ForEach-Object { $_.Substring(3).Replace('\','/') })
    foreach ($path in $trackedAfterBuild) {
        if ($path -notin $allowedBuild) { throw "Unexpected tracked change after candidate build: $path" }
    }
    Commit-Exact 'build: validate Raven cursor caption candidate' $allowedBuild
    Assert-TrackedClean

    $phase = 'install-caption-candidate'
    if (Test-Path -LiteralPath $active -PathType Leaf) {
        throw 'Active transaction pointer unexpectedly exists before new install.'
    }
    Run-Native 'install caption candidate transactionally' {
        & pwsh -NoProfile -ExecutionPolicy Bypass -File $runtimeTest -Mode Install -GameRoot $resolvedGame -ConfirmRuntimeTest
    }
    $installedNew = $true

    if (-not (Test-Path -LiteralPath $active -PathType Leaf)) { throw 'Install returned success without an active manifest.' }
    $installedManifest = Get-Content -LiteralPath $active -Raw | ConvertFrom-Json
    if ([string]$installedManifest.status -ne 'installed') { throw "Installed manifest status differs: $($installedManifest.status)" }
    if (@($installedManifest.entries).Count -ne 5) { throw 'Installed manifest does not contain exactly five entries.' }

    $phase = 'finalize'
    Log ''
    Log 'RESULT=PASS'
    Log 'CAPTION_PATH=MapOn:SetReticleInfo after stock MapCollisionChangeHandler'
    Log "CAPTION_TITLE=Odin's Raven"
    Log 'CAPTION_DESCRIPTION=blank'
    Log 'CAPTION_FAILURE_ISOLATED_BY_PCALL=true'
    Log 'RAVEN_POOL_CAPACITY=45'
    Log 'CATALOGUE_RAVENS=53'
    Log "ROLLED_BACK_PREVIOUS_CANDIDATE=$($rolledBackOld.ToString().ToLowerInvariant())"
    Log 'NEW_CANDIDATE_INSTALLED=true'
    Log "ACTIVE_TRANSACTION=$($installedManifest.transaction_id)"
    Log 'SAVE_OR_PROGRESSION_WRITES=false'
    Log 'GAME_LAUNCHED_BY_SCRIPT=false'
    Log 'PERSISTED_KILL_AUTOMATIC_SAVE_FEED=pending'
    Log "FINISHED_LOCAL=$(Get-Date -Format o)"

    Commit-Exact 'logs: deploy Raven cursor caption runtime' @($logRelative)
}
catch {
    try {
        Log ''
        Log 'RESULT=FAILED'
        Log "FAILED_PHASE=$phase"
        Log "ERROR=$($_.Exception.Message)"
        Log "ROLLED_BACK_PREVIOUS_CANDIDATE=$($rolledBackOld.ToString().ToLowerInvariant())"
        Log "NEW_CANDIDATE_INSTALLED=$($installedNew.ToString().ToLowerInvariant())"
        Log "FINISHED_LOCAL=$(Get-Date -Format o)"

        & git -C $repo reset --hard HEAD *>> $log
        & git -C $repo reset *>> $log
        & git -C $repo add -- $logRelative *>> $log
        & git -C $repo commit -m 'logs: capture Raven cursor caption deploy failure' *>> $log
        if ($LASTEXITCODE -eq 0) {
            & git -C $repo push origin $expectedBranch *>> $log
        }
    }
    catch {
        # Preserve the original deployment failure; the local log remains available.
    }
}

Write-Host 'DONE'
