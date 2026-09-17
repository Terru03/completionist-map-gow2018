param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$branch = 'codex/all-collectibles-production-research'
$sourceRunner = Join-Path $PSScriptRoot 'all-ravens-runtime-test.ps1'
$proofPath = Join-Path $repo 'archive\all-ravens\all-ravens-release-candidate-offline.json'
$candidateRoot = Join-Path $repo 'build\v0.10.5-all-ravens-release-candidate\offline\candidate\game-root'
$stateRoot = Join-Path $repo 'build\v0.10.5-all-ravens-runtime-test\transaction'
$activeManifest = Join-Path $stateRoot 'active.json'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$logDirRel = "archive/field-logs/runtime/all-ravens-realm-fix-resume-$stamp"
$logDir = Join-Path $repo $logDirRel
$log = Join-Path $logDir 'run.txt'
$oldActiveCopy = Join-Path $logDir 'retired-active.json'
$oldTransactionCopy = Join-Path $logDir 'retired-transaction-manifest.json'
$newManifestCopy = Join-Path $logDir 'transaction-manifest.json'

$files = @(
    'exec/dc/pc_le/mapmaster.dcb',
    'exec/dc/pc_le/mapcoords.dcb',
    'exec/dc/pc_le/wad_r_ui.dcb',
    'mods/lua/gameart/ui/scripts/inworldmenu/mapmenu.lua',
    'mods/lua/gameart/scripts/levels/gameplaymodules/progression/precisionchallenge.lua'
)

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $repo

function Log([string]$Text) {
    [IO.File]::AppendAllText($log, $Text + [Environment]::NewLine, (New-Object Text.UTF8Encoding($false)))
}

function Invoke-LoggedExternal {
    param(
        [Parameter(Mandatory=$true)][string]$Label,
        [Parameter(Mandatory=$true)][string]$File,
        [string[]]$Arguments = @()
    )
    Log ''
    Log "=== $Label ==="
    $output = & $File @Arguments 2>&1
    $code = $LASTEXITCODE
    foreach ($line in @($output)) { Log ([string]$line) }
    Log "exit_code=$code"
    if ($code -ne 0) { throw "$Label failed with exit code $code" }
}

function Assert-BaselineGame([object]$Proof) {
    foreach ($relative in $files) {
        $property = $Proof.source_sha256.PSObject.Properties[$relative]
        if ($null -eq $property) { throw "Proof misses source SHA for $relative" }
        $path = Join-Path $GameRoot $relative
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Game baseline file missing: $relative" }
        $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
        $expected = ([string]$property.Value).ToLowerInvariant()
        if ($actual -ne $expected) { throw "Game is not at the restored baseline for $relative" }
    }
}

function Invoke-ForwardedInstall {
    $tempRunner = Join-Path $PSScriptRoot ('.all-ravens-runtime-forwarded-resume-' + $PID + '.ps1')
    try {
        $text = [IO.File]::ReadAllText($sourceRunner)
        $old = '. $engine -LibraryOnly'
        $new = '. $engine -Mode $Mode -GameRoot $GameRoot -ConfirmRuntimeTest:$ConfirmRuntimeTest -LibraryOnly'
        $count = ([regex]::Matches($text, [regex]::Escape($old))).Count
        if ($count -ne 1) { throw "Expected exactly one runtime library import line, found $count." }
        $text = $text.Replace($old, $new)
        [IO.File]::WriteAllText($tempRunner, $text, (New-Object Text.UTF8Encoding($false)))
        Invoke-LoggedExternal -Label 'runtime-install' -File 'pwsh' -Arguments @(
            '-NoProfile','-ExecutionPolicy','Bypass','-File',$tempRunner,
            '-Mode','Install','-GameRoot',$GameRoot,'-ConfirmRuntimeTest'
        )
    }
    finally {
        Remove-Item -LiteralPath $tempRunner -Force -ErrorAction SilentlyContinue
    }
}

function Push-Log([string]$Message) {
    & git add -- $logDirRel | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not stage resume log.' }
    & git commit -m $Message *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Could not commit resume log.' }
    & git push origin $branch *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Could not push resume log.' }
}

"=== ALL-RAVENS REALM-FIX INSTALL RESUME ===" | Set-Content -LiteralPath $log -Encoding utf8
Log "timestamp=$stamp"
Log "branch=$branch"
Log "game=$GameRoot"
Log 'purpose=retire verified rolled-back active pointer, revalidate 53-pool candidate, install corrected build'

try {
    $currentBranch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or $currentBranch -ne $branch) { throw "Expected branch '$branch', got '$currentBranch'." }
    $dirty = & git status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0) { throw 'Could not read Git status.' }
    if ($dirty) { throw 'Tracked checkout is dirty before resume.' }
    if (-not (Test-Path -LiteralPath $GameRoot -PathType Container)) { throw "God of War root not found: $GameRoot" }
    if (-not (Test-Path -LiteralPath $proofPath -PathType Leaf)) { throw 'All-Ravens proof is missing.' }

    $proof = Get-Content -LiteralPath $proofPath -Raw | ConvertFrom-Json
    if (-not [bool]$proof.ready_for_runtime_test) { throw 'Runtime-test gate is closed.' }
    if ([int]$proof.catalogue_entries -ne 53) { throw 'Catalogue count is not 53.' }
    if ([int]$proof.proofs.'exec/dc/pc_le/wad_r_ui.dcb'.raven_capacity_after -ne 53) { throw 'Raven pool capacity is not 53.' }
    Assert-BaselineGame -Proof $proof
    Log 'baseline_source_sha_verification=true'

    if (Test-Path -LiteralPath $activeManifest -PathType Leaf) {
        $old = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
        $oldStatus = [string]$old.status
        if ($oldStatus -notin @('rolled-back','rolled-back-after-install-failure')) {
            throw "Refusing to retire active transaction with status '$oldStatus'."
        }
        if ([string]$old.candidate -ne 'all-ravens-v0.10.5-catalogue-first') {
            throw "Unexpected active transaction candidate '$($old.candidate)'."
        }
        if (@($old.entries).Count -ne 5) { throw 'Rolled-back active transaction does not contain five entries.' }
        $oldTransactionManifest = Join-Path ([string]$old.transaction_root) 'manifest.json'
        if (-not (Test-Path -LiteralPath $oldTransactionManifest -PathType Leaf)) { throw 'Historical transaction manifest is missing.' }
        $history = Get-Content -LiteralPath $oldTransactionManifest -Raw | ConvertFrom-Json
        if ([string]$history.transaction_id -ne [string]$old.transaction_id) { throw 'Active pointer and historical transaction ID differ.' }
        if ([string]$history.status -notin @('rolled-back','rolled-back-after-install-failure')) { throw 'Historical transaction is not rolled back.' }
        Copy-Item -LiteralPath $activeManifest -Destination $oldActiveCopy -Force
        Copy-Item -LiteralPath $oldTransactionManifest -Destination $oldTransactionCopy -Force
        Remove-Item -LiteralPath $activeManifest -Force
        Log "retired_active_transaction=$($old.transaction_id)"
        Log "retired_active_status=$oldStatus"
        Log 'historical_transaction_manifest_preserved=true'
    }
    else {
        Log 'retired_active_transaction=none'
    }

    Invoke-LoggedExternal -Label 'raven-runtime-model-tests' -File 'python' -Arguments @((Join-Path $PSScriptRoot 'test_raven_runtime_model.py'))
    Invoke-LoggedExternal -Label 'all-ravens-lua-tests' -File 'python' -Arguments @((Join-Path $PSScriptRoot 'test_all_ravens_lua.py'))
    Invoke-LoggedExternal -Label 'build-release-candidate' -File 'python' -Arguments @((Join-Path $PSScriptRoot 'build-all-ravens-release-candidate.py'),'--source-root',$GameRoot)
    Invoke-LoggedExternal -Label 'all-ravens-build-tests' -File 'python' -Arguments @((Join-Path $PSScriptRoot 'test_all_ravens_build.py'))
    Invoke-LoggedExternal -Label 'verify-deterministic-rebuild' -File 'python' -Arguments @((Join-Path $PSScriptRoot 'build-all-ravens-release-candidate.py'),'--source-root',$GameRoot,'--check')
    Invoke-LoggedExternal -Label 'fake-game-transaction-tests' -File 'pwsh' -Arguments @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'test-all-ravens-transaction.ps1'))
    Invoke-LoggedExternal -Label 'git-diff-check' -File 'git' -Arguments @('diff','--check')

    $trackedAfterValidation = & git status --porcelain --untracked-files=no
    if ($LASTEXITCODE -ne 0) { throw 'Could not read Git status after validation.' }
    if ($trackedAfterValidation) { throw 'Validation unexpectedly modified tracked source/proof files.' }

    $mapCandidate = Join-Path $candidateRoot 'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
    if (-not (Test-Path -LiteralPath $mapCandidate -PathType Leaf)) { throw 'Candidate mapmenu.lua is missing.' }
    $mapText = [IO.File]::ReadAllText($mapCandidate)
    if (-not $mapText.Contains('local markerLabel = "Odin''s Raven"')) { throw 'Candidate does not contain the visible Raven caption.' }
    if (-not $mapText.Contains('Map.CreateMarkerIcon(info.Id, region, markerLabel)')) { throw 'Candidate does not route the Raven caption into marker creation.' }
    Log 'candidate_caption_verified=true'
    Log 'candidate_raven_pool_capacity=53'

    Invoke-ForwardedInstall

    if (-not (Test-Path -LiteralPath $activeManifest -PathType Leaf)) { throw 'Install finished without an active manifest.' }
    $manifest = Get-Content -LiteralPath $activeManifest -Raw | ConvertFrom-Json
    if ([string]$manifest.status -ne 'installed') { throw "New transaction status is '$($manifest.status)'." }
    if (@($manifest.entries).Count -ne 5) { throw 'New transaction does not contain five entries.' }
    if (@($manifest.entries | Where-Object { [string]$_.write_state -ne 'installed' }).Count -ne 0) { throw 'One or more new transaction entries are not installed.' }
    Copy-Item -LiteralPath $activeManifest -Destination $newManifestCopy -Force

    Log ''
    Log '=== RESULT ==='
    Log 'RESULT=PASS'
    Log "NEW_TRANSACTION_ID=$($manifest.transaction_id)"
    Log 'NEW_TRANSACTION_STATUS=installed'
    Log 'NEW_TRANSACTION_FILES=5'
    Log 'RAVEN_POOL_CAPACITY=53'
    Log "RAVEN_MAP_LABEL=Odin's Raven"
    Log 'OLD_ROLLED_BACK_TRANSACTION_HISTORY_PRESERVED=true'
    Log 'NEXT_FIELD_TEST=realm switching before Raven kill lifecycle'

    Push-Log -Message "logs: capture resumed Raven realm-fix install $stamp"
}
catch {
    Log ''
    Log '=== RESULT ==='
    Log 'RESULT=FAILED'
    Log "ERROR=$($_.Exception.Message)"
    try { Push-Log -Message "logs: capture failed resumed Raven realm-fix install $stamp" } catch { }
}

Write-Host 'DONE'
