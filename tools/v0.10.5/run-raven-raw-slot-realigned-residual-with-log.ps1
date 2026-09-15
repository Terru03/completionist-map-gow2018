param(
    [string]$FrozenRoot = 'C:\Users\david\Documents\GodOfWar-RavenAliveDead-20260915-220250'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$branch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if ([string]::IsNullOrWhiteSpace($repo)) { throw 'Run from inside completionist-map-gow2018 repository.' }
Set-Location $repo

$current = (& git branch --show-current).Trim()
if ($current -ne $branch) { throw "Wrong branch. Expected '$branch', found '$current'." }
if (@(& git diff --cached --name-only).Count -gt 0) { throw 'Pre-existing staged changes exist; analysis refused.' }

& git pull --ff-only origin $branch | Out-Host
if ($LASTEXITCODE -ne 0) { throw 'Branch pull failed.' }

$alive = Join-Path $FrozenRoot 'alive\863677734\game.sav'
$dead = Join-Path $FrozenRoot 'dead\863677734\game.sav'
$scriptPath = Join-Path $repo 'tools\v0.10.5\analyze-raven-raw-slot-realigned-residual.py'
foreach ($p in @($alive,$dead,$scriptPath)) {
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Required file missing: $p" }
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$rel = "archive/field-logs/save-captures/gow-raven-raw-slot-realigned-residual-$stamp"
$out = Join-Path $repo $rel
New-Item -ItemType Directory -Force -Path $out | Out-Null
$json = Join-Path $out 'realigned-residual.json'
$summary = Join-Path $out 'result.txt'
$console = Join-Path $out 'console-log.txt'
$pythonLog = Join-Path $out 'python-output.txt'
$started = $false
$success = $false

function Stop-LocalTranscript {
    if ($script:started) {
        Stop-Transcript | Out-Null
        $script:started = $false
    }
}

try {
    Start-Transcript -LiteralPath $console -Force | Out-Null
    $started = $true
    Write-Host '=== Raven raw-slot realigned residual analysis ==='
    Write-Host 'Offline/read-only. No game launch, no active-save reads, no source writes.'

    $saved = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & python $scriptPath --alive $alive --dead $dead --output-json $json --summary $summary 2>&1 |
            ForEach-Object {
                $line = [string]$_
                Add-Content -LiteralPath $pythonLog -Value $line -Encoding UTF8
                Write-Host $line
            }
        $code = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $saved
    }
    if ($code -ne 0) { throw "Analyzer failed with exit code $code." }
    if (-not (Test-Path -LiteralPath $json -PathType Leaf)) { throw 'Analyzer produced no JSON.' }
    $success = $true
}
catch {
    $_.Exception.ToString() | Set-Content -LiteralPath (Join-Path $out 'error.txt') -Encoding UTF8
    if (-not (Test-Path -LiteralPath $summary)) {
        @('RAVEN_RAW_SLOT_REALIGNED_RESIDUAL_FAILED', "failure=$($_.Exception.Message)") |
            Set-Content -LiteralPath $summary -Encoding UTF8
    }
    Write-Host "REALIGNED_RESIDUAL_FAILED: $($_.Exception.Message)" -ForegroundColor Red
}
finally {
    Stop-LocalTranscript
}

& git add -- $rel
if ($LASTEXITCODE -ne 0) { throw 'Could not stage analysis archive.' }
$staged = @(& git diff --cached --name-only --)
foreach ($p in $staged) {
    if ($p -notlike "$rel/*") { throw "Unexpected staged path outside archive: $p" }
}
if ($staged.Count -gt 0) {
    $msg = if ($success) { 'Archive Raven raw slot realigned residual analysis' } else { 'Archive Raven raw slot realigned residual failure' }
    & git commit -m $msg -- $rel | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Archive commit failed.' }
    & git push origin "HEAD:$branch" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Archive push failed.' }
}
if (-not $success) { exit 1 }
Write-Host 'RAVEN_RAW_SLOT_REALIGNED_RESIDUAL_ARCHIVED' -ForegroundColor Green
