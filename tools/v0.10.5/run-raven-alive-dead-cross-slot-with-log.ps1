param(
    [string]$FrozenRoot = 'C:\Users\david\Documents\GodOfWar-RavenAliveDead-20260915-220250',
    [string]$RelativeSave = '863677734\game.sav'
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

$alive = Join-Path (Join-Path $FrozenRoot 'alive') $RelativeSave
$dead = Join-Path (Join-Path $FrozenRoot 'dead') $RelativeSave
$script = Join-Path $repo 'tools\v0.10.5\analyze-raven-alive-dead-cross-slot.py'
foreach ($path in @($alive,$dead,$script)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required file missing: $path" }
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$relativeOut = "archive/field-logs/save-captures/gow-raven-alive-dead-cross-slot-$stamp"
$out = Join-Path $repo $relativeOut
New-Item -ItemType Directory -Force -Path $out | Out-Null
$json = Join-Path $out 'cross-slot.json'
$md = Join-Path $out 'cross-slot.md'
$summary = Join-Path $out 'summary.txt'
$console = Join-Path $out 'console-log.txt'

Start-Transcript -LiteralPath $console -Force | Out-Null
try {
    Write-Host '=== Raven ALIVE/DEAD frozen-save cross-slot analysis ==='
    Write-Host "ALIVE: $alive"
    Write-Host "DEAD:  $dead"
    Write-Host 'Read-only offline analysis. Active saves are refused by the Python tool.'

    $old = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & python $script --alive $alive --dead $dead --output-json $json --output-md $md --summary $summary 2>&1 |
            ForEach-Object { Write-Host ([string]$_) }
        $code = $LASTEXITCODE
    }
    finally { $ErrorActionPreference = $old }
    if ($code -ne 0) { throw "Cross-slot analyzer failed with exit code $code." }
}
finally {
    try { Stop-Transcript | Out-Null } catch { }
}

& git add -- $relativeOut
if ($LASTEXITCODE -ne 0) { throw 'Could not stage analysis output.' }
$staged = @(& git diff --cached --name-only --)
foreach ($path in $staged) {
    if ($path -notlike "$relativeOut/*") { throw "Unexpected staged path outside analysis output: $path" }
}
if ($staged.Count -gt 0) {
    & git commit -m 'Archive Raven alive-dead cross-slot analysis' -- $relativeOut | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Analysis commit failed.' }
    & git push origin "HEAD:$branch" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Analysis push failed.' }
}

Write-Host ''
Write-Host 'RAVEN_ALIVE_DEAD_CROSS_SLOT_ARCHIVED' -ForegroundColor Green
Get-Content -LiteralPath $summary | ForEach-Object { Write-Host $_ }
