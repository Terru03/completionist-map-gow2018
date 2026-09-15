param(
    [string]$FrozenRoot = 'C:\Users\david\Documents\GodOfWar-RavenForcedManual-20260915-225302'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$branch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if (-not $repo) { throw 'Not inside the repository.' }
Set-Location -LiteralPath $repo

& git pull --ff-only origin $branch | Out-Host

$alive = Join-Path $FrozenRoot 'alive\863677734\game.sav'
$dead  = Join-Path $FrozenRoot 'dead\863677734\game.sav'
if (-not (Test-Path -LiteralPath $alive -PathType Leaf)) { throw "Missing frozen ALIVE save: $alive" }
if (-not (Test-Path -LiteralPath $dead -PathType Leaf)) { throw "Missing frozen DEAD save: $dead" }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outRel = "archive\field-logs\save-captures\gow-raven-forced-manual-chronological-$stamp"
$out = Join-Path $repo $outRel
New-Item -ItemType Directory -Force -Path $out | Out-Null

$log = Join-Path $out 'console-log.txt'
$pyout = Join-Path $out 'python-output.txt'
$json = Join-Path $out 'chronological.json'
$md = Join-Path $out 'chronological.md'
$summary = Join-Path $out 'result.txt'
$analyzer = Join-Path $repo 'tools\v0.10.5\analyze-raven-forced-manual-chronological.py'

Start-Transcript -LiteralPath $log -Force | Out-Null
try {
    Write-Host '=== Raven forced-manual chronological 17 -> 18 diff ==='
    Write-Host 'Pre-kill manual:  22:54:41 (slot 17)'
    Write-Host 'Post-kill manual: 22:55:12 (slot 18)'
    Write-Host 'Offline/read-only. Raw frozen saves are not archived.'

    $old = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & python $analyzer `
        --alive $alive `
        --dead $dead `
        --output-json $json `
        --output-md $md `
        --summary $summary 2>&1 | Tee-Object -FilePath $pyout | Out-Host
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    if ($code -ne 0) { throw "Analyzer failed with exit code $code" }
}
finally {
    Stop-Transcript | Out-Null
}

& git add -- $outRel
& git commit -m 'Archive Raven forced-manual chronological analysis' -- $outRel | Out-Host
& git push origin HEAD:$branch | Out-Host

Write-Host ''
Write-Host 'Raven chronological analysis archived and pushed.' -ForegroundColor Green
Write-Host $outRel
