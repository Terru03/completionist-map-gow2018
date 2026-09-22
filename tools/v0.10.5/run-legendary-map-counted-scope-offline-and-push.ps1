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
if (@(& git diff --cached --name-only).Count -gt 0) {
    throw 'Pre-existing staged changes exist; scope proof refused.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

$Resolver = Join-Path $RepoRoot 'tools\v0.10.5\resolve-legendary-map-counted-scope-offline.py'
$IdentityHelper = Join-Path $RepoRoot 'tools\v0.10.5\legendary_chest_identity.py'
$IdentityTests = Join-Path $RepoRoot 'tools\v0.10.5\test_legendary_chest_identity.py'
$RavenGuard = Join-Path $RepoRoot 'tools\v0.10.5\test-raven-frozen-baseline.ps1'
$Catalogue = Join-Path $RepoRoot 'config\collectibles\v0.10.5\all-collectibles.json'
$Audit = Join-Path $RepoRoot 'docs\research\all-collectibles-native-audit.json'
$Capture = Join-Path $RepoRoot 'archive\field-logs\runtime-captures\staged-wad-bitstream-raven-20260921-060345-c2c9bcc1'

foreach ($required in @(
    $Resolver, $IdentityHelper, $IdentityTests, $RavenGuard, $Catalogue, $Audit,
    (Join-Path $Capture 'report.json')
)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Missing required input: $required"
    }
}

if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object {
    $_.ProcessName -in @('GoW','GodOfWar')
}).Count -gt 0) {
    throw 'Close God of War. This proof is fully offline and does not need the game running.'
}

& $python.Source -m py_compile $Resolver $IdentityHelper $IdentityTests
if ($LASTEXITCODE -ne 0) {
    throw 'Legendary scope Python syntax validation failed.'
}

& $python.Source $IdentityTests
if ($LASTEXITCODE -ne 0) {
    throw 'Legendary identity tests failed before scope proof.'
}

& pwsh -NoProfile -ExecutionPolicy Bypass -File $RavenGuard
if ($LASTEXITCODE -ne 0) {
    throw 'Frozen Raven baseline guard failed.'
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/source-scans/legendary-map-counted-scope-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$outJson = Join-Path $outDir 'report.json'
$outText = Join-Path $outDir 'report.txt'
$console = Join-Path $outDir 'console-log.txt'
$resultFile = Join-Path $outDir 'result.txt'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$exitCode = 0
$failureMessage = ''
Start-Transcript -LiteralPath $console -Force | Out-Null
try {
    Write-Host 'LEGENDARY MAP-COUNTED SCOPE RESOLUTION - OFFLINE' -ForegroundColor Cyan
    Write-Host 'Reconciles physical Legendary identities against native map targets.'
    Write-Host 'Replays the two missing Caldera/Tyr chest states from archived staged data.'
    Write-Host ''

    $resolverArgs = @(
        $Resolver,
        '--catalogue', $Catalogue,
        '--audit', $Audit,
        '--capture-dir', $Capture,
        '--game-root', $GameRoot,
        '--output-json', $outJson,
        '--output-text', $outText
    )
    & $python.Source @resolverArgs
    $resolverExit = $LASTEXITCODE
    if ($resolverExit -ne 0) {
        throw "Legendary map-count scope resolver failed with exit code $resolverExit."
    }

    $report = Get-Content -LiteralPath $outJson -Raw | ConvertFrom-Json
    if ($report.status -ne 'EXACT_33_MAP_COUNTED_SCOPE_RESOLVED') {
        throw "Unexpected scope status: $($report.status)"
    }
    if ([int]$report.corrected_map_counted_production_count -ne 33 -or
        [int]$report.native_region_summary_target_total -ne 33 -or
        [int]$report.production_serialized_identity_count -ne 33 -or
        [int]$report.production_object_hash_count -ne 33) {
        throw 'Corrected 33-marker production accounting failed.'
    }
    if (@($report.overflow_exclusions).Count -ne 2 -or
        @($report.recovered_map_counted_rows).Count -ne 2) {
        throw 'Expected exactly two overflow exclusions and two recovered rows.'
    }
    if (@($report.recovered_map_counted_rows | Where-Object {
        -not [bool]$_.staged_state.exact_match
    }).Count -ne 0) {
        throw 'Recovered Tyr rows did not both match exact staged state carriers.'
    }
    if ([bool]$report.safety.game_process_accessed -or
        [bool]$report.safety.active_save_opened -or
        [bool]$report.safety.save_or_progression_written -or
        [bool]$report.safety.game_files_written -or
        [bool]$report.safety.raven_runtime_modified) {
        throw 'Offline safety contract changed.'
    }

    @(
        'result=LEGENDARY_MAP_COUNTED_SCOPE_PASSED'
        "production_count=$($report.corrected_map_counted_production_count)"
        "native_target_total=$($report.native_region_summary_target_total)"
        "production_serialized_identity_count=$($report.production_serialized_identity_count)"
        "production_object_hash_count=$($report.production_object_hash_count)"
        "overflow_ids=$(@($report.overflow_exclusions.catalogue_id) -join ',')"
        "recovered_ids=$(@($report.recovered_map_counted_rows.catalogue_id) -join ',')"
        'offline_only=true'
        'game_process_accessed=false'
        'save_or_progression_written=false'
        'raven_runtime_modified=false'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
catch {
    $exitCode = 1
    $failureMessage = $_.Exception.Message
    @(
        'result=LEGENDARY_MAP_COUNTED_SCOPE_FAILED'
        "reason=$failureMessage"
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
finally {
    Stop-Transcript | Out-Null
}

& git add -f -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git add scope evidence failed.' }

$message = if ($exitCode -eq 0) {
    "research(v0.10.5): prove Legendary map-counted scope $stamp"
} else {
    "research(v0.10.5): archive Legendary map-counted scope failure $stamp"
}
& git commit -m $message -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git commit scope evidence failed.' }

& git push origin $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push scope evidence failed.' }

$head = (& git rev-parse HEAD).Trim()
if ($exitCode -ne 0) {
    throw "Legendary map-counted scope proof failed; evidence pushed in $head. $failureMessage"
}

Write-Host ''
Write-Host "LEGENDARY_MAP_COUNTED_SCOPE_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
