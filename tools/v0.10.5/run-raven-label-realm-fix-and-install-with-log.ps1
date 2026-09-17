param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = 'codex/all-collectibles-production-research'
$sourceRunner = Join-Path $PSScriptRoot 'all-ravens-runtime-test.ps1'
$patcher = Join-Path $PSScriptRoot 'patch-raven-label-and-realm-transition.py'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logDirRel = "archive/field-logs/runtime/all-ravens-realm-fix-$stamp"
$logDir = Join-Path $repo $logDirRel
$logRel = "$logDirRel/run.txt"
$log = Join-Path $repo $logRel
$manifestRel = "$logDirRel/transaction-manifest.json"
$manifestCopy = Join-Path $repo $manifestRel
$activeManifest = Join-Path $repo 'build\v0.10.5-all-ravens-runtime-test\transaction\active.json'

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $repo

function Log([string]$Text) {
    $Text | Add-Content -LiteralPath $log -Encoding utf8
}

function Invoke-LoggedExternal {
    param(
        [Parameter(Mandatory=$true)][string]$Label,
        [Parameter(Mandatory=$true)][string]$File,
        [string[]]$Arguments = @()
    )
    Log ""
    Log "=== $Label ==="
    $output = & $File @Arguments 2>&1
    $code = $LASTEXITCODE
    foreach ($line in @($output)) { Log ([string]$line) }
    Log "exit_code=$code"
    if ($code -ne 0) { throw "$Label failed with exit code $code" }
}

function Invoke-ForwardedRuntime {
    param(
        [Parameter(Mandatory=$true)][ValidateSet('Install','Rollback')][string]$Mode,
        [switch]$ConfirmRuntimeTest
    )
    $tempRunner = Join-Path $PSScriptRoot ('.all-ravens-runtime-forwarded-' + $PID + '-' + $Mode.ToLowerInvariant() + '.ps1')
    try {
        $text = [IO.File]::ReadAllText($sourceRunner)
        $old = '. $engine -LibraryOnly'
        $new = '. $engine -Mode $Mode -GameRoot $GameRoot -ConfirmRuntimeTest:$ConfirmRuntimeTest -LibraryOnly'
        $count = ([regex]::Matches($text, [regex]::Escape($old))).Count
        if ($count -ne 1) { throw "Expected exactly one runtime library import line, found $count." }
        $text = $text.Replace($old, $new)
        [IO.File]::WriteAllText($tempRunner, $text, (New-Object Text.UTF8Encoding($false)))
        $args = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$tempRunner,'-Mode',$Mode,'-GameRoot',$GameRoot)
        if ($ConfirmRuntimeTest) { $args += '-ConfirmRuntimeTest' }
        Invoke-LoggedExternal -Label ("runtime-" + $Mode.ToLowerInvariant()) -File 'pwsh' -Arguments $args
    }
    finally {
        Remove-Item -LiteralPath $tempRunner -Force -ErrorAction SilentlyContinue
    }
}

function Commit-And-PushLog([string]$Message) {
    & git add -- $logDirRel | Out-Null
    if ($LASTEXITCODE -ne 0) { return }
    & git commit -m $Message *> $null
    if ($LASTEXITCODE -eq 0) {
        & git push origin $branch *> $null
    }
}

"=== ALL-RAVENS LABEL + REALM-TRANSITION FIELD FIX ===" | Set-Content -LiteralPath $log -Encoding utf8
Log "timestamp=$stamp"
Log "branch=$branch"
Log "game=$GameRoot"
Log "field_observation=all Midgard Raven icons visible; captions blank; killed Raven trackable; crash when switching realms"
Log "kill_test_performed=false"
Log "working_hypothesis=45-object Raven UI pool can exhaust during deferred recycle/create overlap on realm transition"
Log "fix=visible Odin's Raven caption + 53-object full-catalogue pool + stale selection disarm on realm change"

$startHead = ''
$sourceCommitted = $false
$rollbackCompleted = $false
try {
    $currentBranch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $currentBranch -ne $branch) { throw "Expected branch '$branch', got '$currentBranch'." }
    $dirty = & git status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0) { throw 'Could not read Git status.' }
    if ($dirty) { throw 'Tracked checkout is dirty before field-fix run.' }
    $startHead = (& git rev-parse HEAD).Trim()
    Log "start_head=$startHead"

    Invoke-ForwardedRuntime -Mode Rollback
    $rollbackCompleted = $true

    Invoke-LoggedExternal -Label 'apply-label-realm-patch' -File 'python' -Arguments @($patcher)
    Invoke-LoggedExternal -Label 'raven-runtime-model-tests' -File 'python' -Arguments @((Join-Path $PSScriptRoot 'test_raven_runtime_model.py'))
    Invoke-LoggedExternal -Label 'all-ravens-lua-tests' -File 'python' -Arguments @((Join-Path $PSScriptRoot 'test_all_ravens_lua.py'))
    Invoke-LoggedExternal -Label 'build-release-candidate' -File 'python' -Arguments @((Join-Path $PSScriptRoot 'build-all-ravens-release-candidate.py'),'--source-root',$GameRoot)
    Invoke-LoggedExternal -Label 'all-ravens-build-tests' -File 'python' -Arguments @((Join-Path $PSScriptRoot 'test_all_ravens_build.py'))
    Invoke-LoggedExternal -Label 'verify-deterministic-rebuild' -File 'python' -Arguments @((Join-Path $PSScriptRoot 'build-all-ravens-release-candidate.py'),'--source-root',$GameRoot,'--check')
    Invoke-LoggedExternal -Label 'fake-game-transaction-tests' -File 'pwsh' -Arguments @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'test-all-ravens-transaction.ps1'))
    Invoke-LoggedExternal -Label 'git-diff-check' -File 'git' -Arguments @('diff','--check')

    Log ""
    Log '=== PRE-INSTALL PROOF CHECK ==='
    $proofPath = Join-Path $repo 'archive\all-ravens\all-ravens-release-candidate-offline.json'
    $proof = Get-Content -LiteralPath $proofPath -Raw | ConvertFrom-Json
    if (-not [bool]$proof.ready_for_runtime_test) { throw 'New proof did not open the runtime-test gate.' }
    if ([int]$proof.catalogue_entries -ne 53) { throw 'New proof catalogue count is not 53.' }
    if ([int]$proof.proofs.'exec/dc/pc_le/wad_r_ui.dcb'.raven_capacity_after -ne 53) { throw 'New proof Raven pool capacity is not 53.' }
    Log 'catalogue_entries=53'
    Log 'raven_pool_capacity=53'
    Log 'ready_for_runtime_test=true'

    $paths = @(
        'tools/v0.10.5/all-ravens-map-runtime.lua',
        'tools/v0.10.5/build-all-ravens-release-candidate.py',
        'tools/v0.10.5/test_all_ravens_build.py',
        'tools/v0.10.5/test_all_ravens_lua.py',
        'archive/all-ravens/all-ravens-release-candidate-offline.json',
        'archive/all-ravens/all-ravens-transaction-self-test.json'
    )
    & git add -- @paths | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage realm-fix source/proof changes.' }
    & git commit -m 'runtime: fix Raven labels and realm-transition capacity' *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Could not commit realm-fix source/proof changes.' }
    $sourceCommitted = $true
    $fixHead = (& git rev-parse HEAD).Trim()
    Log "fix_head=$fixHead"
    & git push origin $branch *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Could not push realm-fix source commit.' }

    Invoke-ForwardedRuntime -Mode Install -ConfirmRuntimeTest

    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) { throw 'Install completed without an active transaction manifest.' }
    Copy-Item -LiteralPath $activeManifest -Destination $manifestCopy -Force
    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    if ([string]$manifest.status -ne 'installed') { throw "New transaction status is '$($manifest.status)', not installed." }
    if (@($manifest.entries).Count -ne 5) { throw 'New transaction does not contain exactly five files.' }
    if (@($manifest.entries | Where-Object { [string]$_.write_state -ne 'installed' }).Count -ne 0) { throw 'One or more new transaction entries are not installed.' }

    Log ""
    Log '=== RESULT ==='
    Log 'RESULT=PASS'
    Log 'NEW_TRANSACTION_STATUS=installed'
    Log 'NEW_TRANSACTION_FILES=5'
    Log 'RAVEN_POOL_CAPACITY=53'
    Log "RAVEN_MAP_LABEL=Odin's Raven"
    Log 'NEXT_FIELD_TEST=realm switching first; Raven kill lifecycle only after realm switch is stable'

    Commit-And-PushLog -Message "logs: capture Raven label/realm fix install $stamp"
}
catch {
    Log ""
    Log '=== RESULT ==='
    Log 'RESULT=FAILED'
    Log "ERROR=$($_.Exception.Message)"
    Log "rollback_completed=$rollbackCompleted"
    Log "source_committed=$sourceCommitted"

    if (-not $sourceCommitted -and -not [string]::IsNullOrWhiteSpace($startHead)) {
        & git reset --hard $startHead *> $null
    }
    Commit-And-PushLog -Message "logs: capture failed Raven label/realm fix $stamp"
}

Write-Host 'DONE'
