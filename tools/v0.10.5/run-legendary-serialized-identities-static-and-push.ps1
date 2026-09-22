[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$ExpectedBranch = 'codex/collectible-legendary-chests'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    throw 'Not inside the Completionist Map repository.'
}
Set-Location $RepoRoot

$branch = (& git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) {
    throw "Wrong branch '$branch'; expected '$ExpectedBranch'."
}

$staged = @(& git diff --cached --name-only)
if ($staged.Count -gt 0) {
    throw "Refusing pre-existing staged changes: $($staged -join ', ')"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

$Resolver = Join-Path $RepoRoot 'tools\v0.10.5\resolve-legendary-serialized-identities-static.py'
$Catalogue = Join-Path $RepoRoot 'config\collectibles\v0.10.5\all-collectibles.json'
$StagedReport = Join-Path $RepoRoot 'archive\field-logs\source-scans\legendary-staged-state-20260922-142029\report.json'
$IdentityTests = Join-Path $RepoRoot 'tools\v0.10.5\test_legendary_chest_identity.py'
$RavenGuard = Join-Path $RepoRoot 'tools\v0.10.5\test-raven-frozen-baseline.ps1'

foreach ($path in @(
    $Resolver,
    $Catalogue,
    $StagedReport,
    $IdentityTests,
    $RavenGuard
)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required file: $path"
    }
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/source-scans/legendary-serialized-identities-static-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$outJson = Join-Path $outDir 'report.json'
$outText = Join-Path $outDir 'report.txt'
$console = Join-Path $outDir 'console-log.txt'
$resultFile = Join-Path $outDir 'result.txt'
$testLog = Join-Path $outDir 'identity-test-log.txt'
$resolverLog = Join-Path $outDir 'resolver-log.txt'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$exitCode = 0
$failureMessage = ''
Start-Transcript -LiteralPath $console -Force | Out-Null
try {
    Write-Host 'LEGENDARY CHEST SERIALIZED IDENTITY RESOLUTION - STATIC / READ ONLY'
    Write-Host 'Uses the audited Legendary catalogue plus the archived staged checkpoint inventory.'
    Write-Host 'No game files or live process are required.'
    Write-Host ''

    & pwsh -NoProfile -ExecutionPolicy Bypass -File $RavenGuard
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven baseline guard failed.' }

    $testLines = @(& $python.Source $IdentityTests 2>&1)
    $testExit = $LASTEXITCODE
    $testLines | ForEach-Object { Write-Host "$_" }
    $testLines | Set-Content -LiteralPath $testLog -Encoding UTF8
    if ($testExit -ne 0) {
        throw "Legendary Chest identity tests failed with exit code $testExit."
    }

    $resolverArgs = @(
        $Resolver,
        '--game-root', $GameRoot,
        '--catalogue', $Catalogue,
        '--staged-report', $StagedReport,
        '--output-json', $outJson,
        '--output-text', $outText
    )
    $resolverLines = [System.Collections.Generic.List[string]]::new()
    & $python.Source @resolverArgs 2>&1 | ForEach-Object {
        $line = "$_"
        $resolverLines.Add($line)
        Write-Host $line
    }
    $resolverExit = $LASTEXITCODE
    $resolverLines | Set-Content -LiteralPath $resolverLog -Encoding UTF8
    if ($resolverExit -ne 0) {
        throw "Legendary serialized identity resolver failed with exit code $resolverExit."
    }

    $report = Get-Content -LiteralPath $outJson -Raw | ConvertFrom-Json
    if ($report.status -ne 'EXACT_32_OF_32_STAGED_BINDING') {
        throw "Unexpected resolution status: $($report.status)"
    }
    if (-not [bool]$report.unique_exact_binding) {
        throw 'Legendary staged binding is not uniquely exact.'
    }
    if ([int]$report.best_match_count -ne 32) {
        throw "Expected 32/32 staged matches; got $($report.best_match_count)/32."
    }
    if ([int]$report.identities.Count -ne 33) {
        throw "Expected 33 derived Legendary identities; got $($report.identities.Count)."
    }
    $matched = @($report.identities | Where-Object { [bool]$_.staged_simple_state_match }).Count
    if ($matched -ne 32) {
        throw "Expected 32 derived identities to match frozen staged state; got $matched."
    }
    $uniqueHashes = @($report.identities.object_hash_hex | Sort-Object -Unique).Count
    if ($uniqueHashes -ne 33) {
        throw "Expected 33 unique Legendary object hashes; got $uniqueHashes."
    }
    if ([bool]$report.state_semantics_proven) {
        throw 'Identity resolution must not prematurely claim OPENED state semantics.'
    }
    if (-not [bool]$report.safety.static_game_files_read_only -or
        -not [bool]$report.safety.archived_checkpoint_only -or
        [bool]$report.safety.process_accessed -or
        [bool]$report.safety.active_save_opened -or
        [bool]$report.safety.save_or_progression_written -or
        [bool]$report.safety.game_files_written -or
        [bool]$report.safety.raven_runtime_modified) {
        throw 'Static/safety contract changed.'
    }

    @(
        'result=LEGENDARY_SERIALIZED_IDENTITY_RESOLUTION_PASSED'
        'staged_binding=32/32'
        'derived_identities=33'
        "identity_rule=$($report.winner.scene_grammar)"
        "own_identity_hex=$($report.winner.prototype_identity_hex)"
        "simple_state_parent_count=$($report.simple_state_oracle.parent_count)"
        'state_semantics_proven=false'
        'process_accessed=false'
        'active_save_opened=false'
        'save_or_progression_written=false'
        'game_files_written=false'
        'raven_runtime_modified=false'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
catch {
    $exitCode = 1
    $failureMessage = $_.Exception.Message
    @(
        'result=LEGENDARY_SERIALIZED_IDENTITY_RESOLUTION_FAILED'
        "reason=$failureMessage"
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
finally {
    Stop-Transcript | Out-Null
}

& git add -f -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git add evidence failed' }

$message = if ($exitCode -eq 0) {
    "research(v0.10.5): resolve Legendary serialized identities static $stamp"
} else {
    "research(v0.10.5): archive Legendary serialized identity resolution failure $stamp"
}
& git commit -m $message -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git commit evidence failed' }
& git push origin $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push evidence failed' }
$head = (& git rev-parse HEAD).Trim()

if ($exitCode -ne 0) {
    throw "Legendary serialized identity resolution failed; evidence pushed in $head. $failureMessage"
}

Write-Host ''
Write-Host "LEGENDARY_SERIALIZED_IDENTITY_RESOLUTION_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
