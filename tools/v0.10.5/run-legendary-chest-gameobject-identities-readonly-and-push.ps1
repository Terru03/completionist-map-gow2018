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

$Capture = Join-Path $RepoRoot 'tools\v0.10.5\capture-legendary-chest-gameobject-identities-readonly.py'
$Catalogue = Join-Path $RepoRoot 'config\collectibles\v0.10.5\all-collectibles.json'
$StaticTest = Join-Path $RepoRoot 'tools\v0.10.5\test_legendary_chest_identity.py'
$RavenGuard = Join-Path $RepoRoot 'tools\v0.10.5\test-raven-frozen-baseline.ps1'

foreach ($path in @($Capture, $Catalogue, $StaticTest, $RavenGuard, (Join-Path $GameRoot 'GoW.exe'))) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required file: $path"
    }
}

$running = @(
    Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -in @('GoW', 'GodOfWar') }
)
if ($running.Count -ne 1) {
    throw 'Start God of War and load any save before running this proof.'
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/legendary-chest-gameobject-identities-readonly-$stamp"
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
    Write-Host 'LEGENDARY CHEST IDENTITY PROOF - READ ONLY'
    Write-Host 'No gameplay action is required.'
    Write-Host 'Uses ReadProcessMemory only; no process/save/progression writes.'
    Write-Host ''

    & pwsh -NoProfile -ExecutionPolicy Bypass -File $RavenGuard
    if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven baseline guard failed.' }

    & $python.Source $StaticTest
    if ($LASTEXITCODE -ne 0) { throw 'Legendary Chest static identity tests failed.' }

    $captureArgs = @(
        $Capture,
        '--game-root', $GameRoot,
        '--catalogue', $Catalogue,
        '--output-json', $outJson,
        '--output-text', $outText
    )
    & $python.Source @captureArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Legendary Chest read-only identity sweep failed with exit code $LASTEXITCODE."
    }

    $report = Get-Content -LiteralPath $outJson -Raw | ConvertFrom-Json
    if ($report.result -ne 'ALL_33_TRACKED_LEGENDARY_CHEST_GAMEOBJECT_IDENTITIES_RESOLVED') {
        throw "Unexpected proof result: $($report.result)"
    }
    if ([int]$report.resolved_count -ne 33 -or [int]$report.missing_count -ne 0) {
        throw 'Legendary Chest identity proof did not resolve exactly 33/33.'
    }
    if (-not [bool]$report.source_identity_checks.all_exact) {
        throw 'Legendary Chest WAD identity checks were not exact.'
    }
    if ([bool]$report.safety.process_memory_written -or
        [bool]$report.safety.save_or_progression_written -or
        [bool]$report.safety.game_files_written) {
        throw 'Safety contract changed.'
    }

    @(
        'result=LEGENDARY_CHEST_IDENTITY_PROOF_PASSED'
        'resolved=33'
        'missing=0'
        "prototype_identity_elements=$($report.prototype_identity_elements_hex -join ',')"
        'process_memory_written=false'
        'save_or_progression_written=false'
        'game_files_written=false'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
catch {
    $exitCode = 1
    $failureMessage = $_.Exception.Message
    @(
        'result=LEGENDARY_CHEST_IDENTITY_PROOF_FAILED'
        "reason=$failureMessage"
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
finally {
    Stop-Transcript | Out-Null
}

& git add -f -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git add evidence failed' }
$message = if ($exitCode -eq 0) {
    "research(v0.10.5): prove 33 Legendary Chest GameObject identities $stamp"
} else {
    "research(v0.10.5): archive Legendary Chest identity proof failure $stamp"
}
& git commit -m $message -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git commit evidence failed' }
& git push origin $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push evidence failed' }
$head = (& git rev-parse HEAD).Trim()

if ($exitCode -ne 0) {
    throw "Legendary Chest identity proof failed; evidence pushed in $head. $failureMessage"
}

Write-Host ''
Write-Host "LEGENDARY_CHEST_IDENTITY_PROOF_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
