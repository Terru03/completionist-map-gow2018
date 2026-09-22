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
    throw 'Pre-existing staged changes exist; capture refused.'
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { throw 'python.exe was not found in PATH.' }

$Capture = Join-Path $RepoRoot 'tools\v0.10.5\capture-legendary-live-wad-contexts-readonly.py'
$Catalogue = Join-Path $RepoRoot 'config\collectibles\v0.10.5\all-collectibles.json'
$RavenGuard = Join-Path $RepoRoot 'tools\v0.10.5\test-raven-frozen-baseline.ps1'
$ExePath = Join-Path $GameRoot 'GoW.exe'

foreach ($path in @($Capture, $Catalogue, $RavenGuard, $ExePath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing required file: $path"
    }
}

& pwsh -NoProfile -ExecutionPolicy Bypass -File $RavenGuard
if ($LASTEXITCODE -ne 0) { throw 'Frozen Raven baseline guard failed.' }

$expectedFull = [System.IO.Path]::GetFullPath($ExePath)
$game = $null
foreach ($candidate in @(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') })) {
    $candidatePath = $null
    try { $candidatePath = $candidate.Path } catch { }
    if ([string]::IsNullOrWhiteSpace($candidatePath)) {
        try { $candidatePath = $candidate.MainModule.FileName } catch { }
    }
    if ([string]::IsNullOrWhiteSpace($candidatePath)) { continue }
    try { $candidateFull = [System.IO.Path]::GetFullPath($candidatePath) } catch { continue }
    if ([string]::Equals($candidateFull, $expectedFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        $game = $candidate
        break
    }
}
if ($null -eq $game) {
    throw 'Start God of War and load a save before running this read-only capture.'
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeDir = "archive/field-logs/runtime-captures/legendary-live-wad-contexts-$stamp"
$outDir = Join-Path $RepoRoot ($relativeDir -replace '/', [IO.Path]::DirectorySeparatorChar)
$outJson = Join-Path $outDir 'report.json'
$outText = Join-Path $outDir 'report.txt'
$console = Join-Path $outDir 'console-log.txt'
$captureLog = Join-Path $outDir 'capture-log.txt'
$resultFile = Join-Path $outDir 'result.txt'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$exitCode = 0
$failureMessage = ''
Start-Transcript -LiteralPath $console -Force | Out-Null
try {
    Write-Host 'LEGENDARY LIVE WAD CONTEXT INVENTORY - READ ONLY'
    Write-Host "Using GoW PID $($game.Id)."
    Write-Host 'No gameplay action is required.'
    Write-Host 'Uses PROCESS_QUERY_INFORMATION + PROCESS_VM_READ only.'
    Write-Host ''

    $argsList = @(
        $Capture,
        '--pid', [string]$game.Id,
        '--exe', $ExePath,
        '--catalogue', $Catalogue,
        '--output-json', $outJson,
        '--output-text', $outText
    )
    $lines = [System.Collections.Generic.List[string]]::new()
    & $python.Source @argsList 2>&1 | ForEach-Object {
        $line = "$_"
        $lines.Add($line)
        Write-Host $line
    }
    $captureExit = $LASTEXITCODE
    $lines | Set-Content -LiteralPath $captureLog -Encoding UTF8
    if ($captureExit -ne 0) {
        throw "Legendary live WAD context capture failed with exit code $captureExit."
    }

    $report = Get-Content -LiteralPath $outJson -Raw | ConvertFrom-Json
    if ([int]$report.tracked_catalogue_count -ne 33 -or [int]$report.tracked_wad_count -ne 27) {
        throw 'Legendary tracked catalogue/WAD contract changed.'
    }
    if ([bool]$report.safety.process_writes -or
        [bool]$report.safety.save_writes -or
        [bool]$report.safety.progression_writes -or
        [bool]$report.safety.game_files_written -or
        [bool]$report.safety.raven_runtime_modified) {
        throw 'Safety contract changed.'
    }

    @(
        'result=LEGENDARY_LIVE_WAD_CONTEXT_INVENTORY_CAPTURED'
        "capture_result=$($report.result)"
        "live_context_count=$($report.live_context_count)"
        "decoded_name_count=$($report.decoded_name_count)"
        "tracked_live_context_count=$($report.tracked_live_context_count)"
        "tracked_live_wad_count=$($report.tracked_live_wad_count)"
        "tracked_live_wad_names=$(@($report.tracked_live_wad_names) -join ',')"
        'process_writes=false'
        'save_writes=false'
        'progression_writes=false'
        'game_files_written=false'
        'raven_runtime_modified=false'
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
catch {
    $exitCode = 1
    $failureMessage = $_.Exception.Message
    @(
        'result=LEGENDARY_LIVE_WAD_CONTEXT_INVENTORY_FAILED'
        "reason=$failureMessage"
    ) | Set-Content -LiteralPath $resultFile -Encoding UTF8
}
finally {
    Stop-Transcript | Out-Null
}

& git add -f -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git add evidence failed' }

$message = if ($exitCode -eq 0) {
    "research(v0.10.5): capture Legendary live WAD contexts $stamp"
} else {
    "research(v0.10.5): archive Legendary live WAD context failure $stamp"
}
& git commit -m $message -- $relativeDir
if ($LASTEXITCODE -ne 0) { throw 'git commit evidence failed' }
& git push origin $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push evidence failed' }
$head = (& git rev-parse HEAD).Trim()

if ($exitCode -ne 0) {
    throw "Legendary live WAD context capture failed; evidence pushed in $head. $failureMessage"
}

Write-Host ''
Write-Host "LEGENDARY_LIVE_WAD_CONTEXTS_PUSHED $head" -ForegroundColor Green
Write-Host "Evidence: $relativeDir"
