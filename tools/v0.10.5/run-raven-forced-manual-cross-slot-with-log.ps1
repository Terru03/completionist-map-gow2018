param(
    [Parameter(Mandatory = $true)]
    [string]$FrozenRoot
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot '..\..'))

$frozen = (Resolve-Path -LiteralPath $FrozenRoot).Path
$aliveCandidates = @(Get-ChildItem -LiteralPath (Join-Path $frozen 'alive') -Filter 'game.sav' -File -Recurse)
$deadCandidates  = @(Get-ChildItem -LiteralPath (Join-Path $frozen 'dead')  -Filter 'game.sav' -File -Recurse)
if ($aliveCandidates.Count -ne 1 -or $deadCandidates.Count -ne 1) {
    throw "Expected exactly one game.sav under alive and dead. alive=$($aliveCandidates.Count) dead=$($deadCandidates.Count)"
}
$alive = $aliveCandidates[0].FullName
$dead = $deadCandidates[0].FullName

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outRel = "archive\field-logs\save-captures\gow-raven-forced-manual-cross-slot-$stamp"
$out = Join-Path (Get-Location) $outRel
New-Item -ItemType Directory -Force -Path $out | Out-Null
$log = Join-Path $out 'console-log.txt'

Start-Transcript -Path $log -Force | Out-Null
try {
    Write-Host '=== Raven forced-manual frozen-save cross-slot analysis ==='
    Write-Host "ALIVE: $alive"
    Write-Host "DEAD:  $dead"
    Write-Host 'Offline/read-only analysis. Raw frozen saves are not archived.'

    $json = Join-Path $out 'cross-slot.json'
    $md = Join-Path $out 'cross-slot.md'
    $summary = Join-Path $out 'result.txt'
    $pythonOut = Join-Path $out 'python-output.txt'

    & python '.\tools\v0.10.5\analyze-raven-alive-dead-cross-slot.py' `
        --alive $alive `
        --dead $dead `
        --output-json $json `
        --output-md $md `
        --summary $summary 2>&1 | Tee-Object -FilePath $pythonOut
    if ($LASTEXITCODE -ne 0) {
        throw "Cross-slot analyzer failed with exit code $LASTEXITCODE"
    }
}
finally {
    Stop-Transcript | Out-Null
}

git add -- $outRel
git commit -m 'Archive Raven forced-manual cross-slot analysis' -- $outRel
if ($LASTEXITCODE -ne 0) { throw 'git commit failed' }
git push origin HEAD:codex/all-collectibles-production-research
if ($LASTEXITCODE -ne 0) { throw 'git push failed' }

Write-Host ''
Write-Host 'FORCED_MANUAL_ANALYSIS_PUSHED' -ForegroundColor Green
Write-Host $outRel
