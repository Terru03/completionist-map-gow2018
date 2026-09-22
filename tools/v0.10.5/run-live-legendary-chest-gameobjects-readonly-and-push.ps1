[CmdletBinding()]
param(
    [string]$GameRoot = 'G:\SteamLibrary\steamapps\common\GodOfWar',
    [string]$ExpectedBranch = 'codex/collectible-legendary-chests'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepoRoot = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($RepoRoot)) { throw 'Not inside the Completionist Map repository.' }
Set-Location $RepoRoot

$branch = (& git branch --show-current).Trim()
if ($branch -ne $ExpectedBranch) { throw "Wrong branch '$branch'; expected '$ExpectedBranch'." }
if (@(& git diff --cached --name-only).Count -gt 0) { throw 'Pre-existing staged changes exist; capture refused.' }

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

$Capture = Join-Path $RepoRoot 'tools\v0.10.5\capture-live-legendary-chest-gameobjects-readonly.py'
$Catalogue = Join-Path $RepoRoot 'config\collectibles\v0.10.5\all-collectibles.json'
$RavenGuard = Join-Path $RepoRoot 'tools\v0.10.5\test-raven-frozen-baseline.ps1'
foreach ($required in @($Capture, $Catalogue, $RavenGuard)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Missing required file: $required" }
}

& $python.Source -m py_compile $Capture
if ($LASTEXITCODE -ne 0) { throw 'Live Legendary capture script failed Python syntax validation.' }

& pwsh -NoProfile -ExecutionPolicy Bypass -File $RavenGuard
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven baseline guard failed.' }

$running = @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') })
if ($running.Count -ne 1) { throw 'Keep God of War running on the currently loaded Mountain save before running this capture.' }

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/live-legendary-gameobjects-$stamp"
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
    Write-Host 'LIVE LEGENDARY CHEST GAMEOBJECT CAPTURE - READ ONLY'
    Write-Host 'Keep the current Mountain area loaded. No gameplay action is required.'
    Write-Host 'Captures exact resident registry/slot/token/object identities only.'
    Write-Host ''

    $captureArgs = @($Capture, '--game-root', $GameRoot, '--catalogue', $Catalogue, '--output-json', $outJson, '--output-text', $outText)
    & $python.Source @captureArgs
    $captureExit = $LASTEXITCODE
    if ($captureExit -ne 0) { throw "Live Legendary GameObject capture failed with exit code $captureExit." }

    $report = Get-Content -LiteralPath $outJson -Raw | ConvertFrom-Json
    if ([int]$report.tracked_catalogue_count -ne 33) { throw "Expected 33 tracked Legendary rows; got $($report.tracked_catalogue_count)." }
    if ([bool]$report.safety.process_memory_written -or [bool]$report.safety.active_save_opened -or [bool]$report.safety.save_or_progression_written -or [bool]$report.safety.game_files_written -or [bool]$report.safety.raven_runtime_modified) { throw 'Read-only safety contract changed.' }

    @(
        'result=LIVE_LEGENDARY_GAMEOBJECT_CAPTURED'
        "capture_result=$($report.result)"
        "tracked_live_wad_count=$(@($report.tracked_live_wad_registry_pairs).Count)"
        "exact_live_chest_count=$($report.exact_live_chest_count)"
        "mountain_exact_live_chest_count=$($report.mountain_exact_live_chest_count)"
        "exact_live_catalogue_ids=$(@($report.exact_live_catalogue_ids) -join ',')"
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
        'result=LIVE_LEGENDARY_GAMEOBJECT_CAPTURE_FAILED'
        "reason=$failureMessage"
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
finally {
    Stop-Transcript | Out-Null
}

& git add -f -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git add capture evidence failed.' }

$message = if ($exitCode -eq 0) { "research(v0.10.5): capture live Legendary GameObject ids $stamp" } else { "research(v0.10.5): archive live Legendary GameObject capture failure $stamp" }
& git commit -m $message -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git commit capture evidence failed.' }

& git push origin $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push capture evidence failed.' }

$head = (& git rev-parse HEAD).Trim()
if ($exitCode -ne 0) { throw "Live Legendary GameObject capture failed; evidence pushed in $head. $failureMessage" }

Write-Host ''
Write-Host "LIVE_LEGENDARY_GAMEOBJECT_CAPTURE_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
