[CmdletBinding()]
param(
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

$Analyzer = Join-Path $RepoRoot 'tools\v0.10.5\analyze-legendary-staged-state.py'
$Catalogue = Join-Path $RepoRoot 'config\collectibles\v0.10.5\all-collectibles.json'
$Capture = Join-Path $RepoRoot 'archive\field-logs\runtime-captures\staged-wad-bitstream-raven-20260921-060345-c2c9bcc1'
$RavenGuard = Join-Path $RepoRoot 'tools\v0.10.5\test-raven-frozen-baseline.ps1'

foreach ($path in @($Analyzer, $Catalogue, $RavenGuard)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required file: $path"
    }
}
if (-not (Test-Path -LiteralPath $Capture -PathType Container)) {
    throw "Missing frozen staged WAD capture: $Capture"
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/source-scans/legendary-staged-state-$stamp"
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
    Write-Host 'LEGENDARY CHEST STAGED STATE INVENTORY - OFFLINE'
    Write-Host 'Uses the already archived staged WAD capture. GoW does not need to be running.'
    Write-Host ''

    & pwsh -NoProfile -ExecutionPolicy Bypass -File $RavenGuard
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven baseline guard failed.' }

    $argsList = @(
        $Analyzer,
        '--capture-dir', $Capture,
        '--catalogue', $Catalogue,
        '--output-json', $outJson,
        '--output-text', $outText
    )
    $lines = @(& $python.Source @argsList 2>&1)
    $analyzerExit = $LASTEXITCODE
    $lines | ForEach-Object { Write-Host "$_" }
    if ($analyzerExit -ne 0) {
        throw "Legendary staged-state analyzer failed with exit code $analyzerExit."
    }

    $report = Get-Content -LiteralPath $outJson -Raw | ConvertFrom-Json
    if ([int]$report.tracked_catalogue_count -ne 33) {
        throw "Tracked Legendary count changed: $($report.tracked_catalogue_count)"
    }
    if ([int]$report.capture_present_catalogue_count -ne 32) {
        throw "Expected frozen capture to represent 32 tracked Legendary rows; got $($report.capture_present_catalogue_count)"
    }
    if ([bool]$report.interpretation.legendary_binding_proven -or
        [bool]$report.interpretation.state_semantics_proven) {
        throw 'Inventory must not claim Legendary binding or state semantics.'
    }
    if (-not [bool]$report.safety.offline_only -or
        [bool]$report.safety.game_process_accessed -or
        [bool]$report.safety.save_or_progression_written -or
        [bool]$report.safety.game_files_written -or
        [bool]$report.safety.raven_decoder_modified) {
        throw 'Offline/safety contract changed.'
    }

    @(
        'result=LEGENDARY_STAGED_STATE_INVENTORY_PASSED'
        "tracked_catalogue_count=$($report.tracked_catalogue_count)"
        "capture_present_catalogue_count=$($report.capture_present_catalogue_count)"
        "capture_present_wad_count=$($report.capture_present_wad_count)"
        "total_state_entries=$($report.total_state_entries)"
        "schema_signature_count=$($report.schema_signature_count)"
        'legendary_binding_proven=false'
        'state_semantics_proven=false'
        'offline_only=true'
        'raven_decoder_modified=false'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
catch {
    $exitCode = 1
    $failureMessage = $_.Exception.Message
    @(
        'result=LEGENDARY_STAGED_STATE_INVENTORY_FAILED'
        "reason=$failureMessage"
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
finally {
    Stop-Transcript | Out-Null
}

& git add -f -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git add evidence failed' }

$message = if ($exitCode -eq 0) {
    "research(v0.10.5): inventory Legendary staged state $stamp"
} else {
    "research(v0.10.5): archive Legendary staged state inventory failure $stamp"
}
& git commit -m $message -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git commit evidence failed' }
& git push origin $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push evidence failed' }
$head = (& git rev-parse HEAD).Trim()

if ($exitCode -ne 0) {
    throw "Legendary staged-state inventory failed; evidence pushed in $head. $failureMessage"
}

Write-Host ''
Write-Host "LEGENDARY_STAGED_STATE_INVENTORY_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
