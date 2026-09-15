param(
    [string]$FrozenRoot = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$branch = 'codex/all-collectibles-production-research'
$repo = (& git rev-parse --show-toplevel 2>$null).Trim()
if (-not $repo) { throw 'Not inside the repository.' }
Set-Location $repo

& git pull --ff-only origin $branch | Out-Host

if (-not $FrozenRoot) {
    $FrozenRoot = Get-ChildItem (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'GodOfWar-RavenForcedManual-*') -Directory |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $FrozenRoot -or -not (Test-Path -LiteralPath $FrozenRoot)) {
    throw 'Frozen Raven forced-manual root not found.'
}

$pre = Get-ChildItem (Join-Path $FrozenRoot 'alive') -Filter 'game.sav' -File -Recurse | Select-Object -First 1
$post = Get-ChildItem (Join-Path $FrozenRoot 'dead') -Filter 'game.sav' -File -Recurse | Select-Object -First 1
if (-not $pre -or -not $post) { throw 'Frozen pre/post game.sav pair not found.' }

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outRel = "archive\field-logs\save-captures\gow-raven-forced-manual-stream-structure-$stamp"
$out = Join-Path $repo $outRel
New-Item -ItemType Directory -Force -Path $out | Out-Null

$log = Join-Path $out 'console-log.txt'
Start-Transcript -Path $log -Force | Out-Null
try {
    Write-Host '=== Raven forced-manual stream structure probe ==='
    Write-Host "Frozen root: $FrozenRoot"
    Write-Host 'Offline/read-only. Raw save/stream bytes are not archived.'

    $json = Join-Path $out 'stream-structure.json'
    $summary = Join-Path $out 'result.txt'
    $pylog = Join-Path $out 'python-output.txt'

    & python '.\tools\v0.10.5\analyze-raven-forced-manual-stream-structure.py' `
        --pre $pre.FullName `
        --post $post.FullName `
        --output-json $json `
        --summary $summary 2>&1 | Tee-Object -FilePath $pylog

    if ($LASTEXITCODE -ne 0) { throw "Analyzer failed with exit code $LASTEXITCODE" }
}
finally {
    Stop-Transcript | Out-Null
}

git add -- $outRel
git commit -m 'Archive Raven manual-save stream structure analysis' -- $outRel | Out-Host
git push origin HEAD:$branch | Out-Host

Write-Host ''
Write-Host 'STREAM STRUCTURE ANALYSIS PUSHED.' -ForegroundColor Green
