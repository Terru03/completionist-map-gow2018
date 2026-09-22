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

$Capture = Join-Path $RepoRoot 'tools\v0.10.5\capture-legendary-staged-runtime-identity-intersection-readonly.py'
$Catalogue = Join-Path $RepoRoot 'config\collectibles\v0.10.5\all-collectibles.json'
$StagedReport = Join-Path $RepoRoot 'archive\field-logs\source-scans\legendary-staged-state-20260922-142029\report.json'
$StaticTest = Join-Path $RepoRoot 'tools\v0.10.5\test_legendary_chest_identity.py'
$RavenGuard = Join-Path $RepoRoot 'tools\v0.10.5\test-raven-frozen-baseline.ps1'

foreach ($path in @(
    $Capture,
    $Catalogue,
    $StagedReport,
    $StaticTest,
    $RavenGuard,
    (Join-Path $GameRoot 'GoW.exe')
)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required file: $path"
    }
}

$running = @(
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }
)
if ($running.Count -ne 1) {
    throw 'Start God of War and load a save before running this read-only capture.'
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/legendary-staged-runtime-identity-intersection-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$outJson = Join-Path $outDir 'report.json'
$outText = Join-Path $outDir 'report.txt'
$console = Join-Path $outDir 'console-log.txt'
$resultFile = Join-Path $outDir 'result.txt'
$staticLog = Join-Path $outDir 'static-test-log.txt'
$captureLog = Join-Path $outDir 'capture-log.txt'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$exitCode = 0
$failureMessage = ''
Start-Transcript -LiteralPath $console -Force | Out-Null
try {
    Write-Host 'LEGENDARY STAGED/RUNTIME IDENTITY INTERSECTION - READ ONLY'
    Write-Host 'Keep God of War running on a loaded save.'
    Write-Host 'No gameplay action is required during the sweep.'
    Write-Host 'Uses ReadProcessMemory only; no process/save/progression writes.'
    Write-Host ''

    & pwsh -NoProfile -ExecutionPolicy Bypass -File $RavenGuard
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven baseline guard failed.' }

    $staticLines = @(& $python.Source $StaticTest 2>&1)
    $staticExit = $LASTEXITCODE
    $staticLines | ForEach-Object { Write-Host "$_" }
    $staticLines | Set-Content -LiteralPath $staticLog -Encoding UTF8
    if ($staticExit -ne 0) {
        throw "Legendary Chest static tests failed with exit code $staticExit."
    }

    $captureArgs = @(
        $Capture,
        '--game-root', $GameRoot,
        '--catalogue', $Catalogue,
        '--staged-report', $StagedReport,
        '--output-json', $outJson,
        '--output-text', $outText
    )
    $captureLines = [System.Collections.Generic.List[string]]::new()
    & $python.Source @captureArgs 2>&1 | ForEach-Object {
        $line = "$_"
        $captureLines.Add($line)
        Write-Host $line
    }
    $captureExit = $LASTEXITCODE
    $captureLines | Set-Content -LiteralPath $captureLog -Encoding UTF8
    if ($captureExit -ne 0) {
        throw "Legendary staged/runtime intersection failed with exit code $captureExit."
    }

    $report = Get-Content -LiteralPath $outJson -Raw | ConvertFrom-Json
    if ([int]$report.staged_oracle.dominant_parent_count -ne 206) {
        throw "Expected 206 staged dominant parents; got $($report.staged_oracle.dominant_parent_count)."
    }
    if ([bool]$report.safety.process_memory_written -or
        [bool]$report.safety.active_save_opened -or
        [bool]$report.safety.save_or_progression_written -or
        [bool]$report.safety.game_files_written -or
        [bool]$report.safety.raven_runtime_modified) {
        throw 'Safety contract changed.'
    }

    if ([int]$report.hit_count -lt 1) {
        throw 'No resident registry-238 identity matched the 206 staged dominant state hashes.'
    }

    @(
        'result=LEGENDARY_STAGED_RUNTIME_INTERSECTION_FOUND'
        "hits=$($report.hit_count)"
        "represented_wads=$($report.represented_wads.Count)"
        "catalogue_overlap_hits=$($report.catalogue_overlap_hit_count)"
        'process_memory_written=false'
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
        'result=LEGENDARY_STAGED_RUNTIME_INTERSECTION_FAILED'
        "reason=$failureMessage"
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
finally {
    Stop-Transcript | Out-Null
}

& git add -f -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git add evidence failed' }

$message = if ($exitCode -eq 0) {
    "research(v0.10.5): capture Legendary staged runtime identity intersection $stamp"
} else {
    "research(v0.10.5): archive Legendary staged runtime intersection failure $stamp"
}
& git commit -m $message -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git commit evidence failed' }
& git push origin $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push evidence failed' }
$head = (& git rev-parse HEAD).Trim()

if ($exitCode -ne 0) {
    throw "Legendary staged/runtime intersection failed; evidence pushed in $head. $failureMessage"
}

Write-Host ''
Write-Host "LEGENDARY_STAGED_RUNTIME_INTERSECTION_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
