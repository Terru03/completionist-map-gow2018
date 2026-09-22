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
if (@(Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -in @('GoW','GodOfWar') }).Count -gt 0) {
    throw 'Close God of War before restoring the temporary route marker.'
}

$backupRoot = Join-Path $GameRoot 'mods\completionist-map\diagnostic-backups\legendary-route-peak500'
$manifestPath = Join-Path $backupRoot 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Legendary route backup manifest not found: $manifestPath"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json

$relativeFiles = @(
    'exec\dc\pc_le\mapmaster.dcb',
    'exec\dc\pc_le\mapcoords.dcb',
    'mods\lua\gameart\ui\scripts\inworldmenu\mapmenu.lua'
)
foreach ($relative in $relativeFiles) {
    $backup = Join-Path $backupRoot $relative
    if (-not (Test-Path -LiteralPath $backup -PathType Leaf)) {
        throw "Diagnostic backup file missing: $backup"
    }
}

$stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd-HHmmss')
$relativeEvidence = "archive/field-logs/runtime-captures/legendary-test-route-marker-restore-$stamp"
$evidence = Join-Path $RepoRoot ($relativeEvidence -replace '/', [IO.Path]::DirectorySeparatorChar)
New-Item -ItemType Directory -Force -Path $evidence | Out-Null
$console = Join-Path $evidence 'console-log.txt'

Start-Transcript -LiteralPath $console -Force | Out-Null
try {
    Write-Host 'LEGENDARY TEST ROUTE MARKER - EXACT RESTORE' -ForegroundColor Cyan

    foreach ($relative in $relativeFiles) {
        $backup = Join-Path $backupRoot $relative
        $target = Join-Path $GameRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        [IO.File]::WriteAllBytes($target, [IO.File]::ReadAllBytes($backup))
    }

    $actualMaster = (Get-FileHash -LiteralPath (Join-Path $GameRoot $relativeFiles[0]) -Algorithm SHA256).Hash.ToLowerInvariant()
    $actualCoords = (Get-FileHash -LiteralPath (Join-Path $GameRoot $relativeFiles[1]) -Algorithm SHA256).Hash.ToLowerInvariant()
    $actualLua = (Get-FileHash -LiteralPath (Join-Path $GameRoot $relativeFiles[2]) -Algorithm SHA256).Hash.ToLowerInvariant()

    $expectedMaster = [string]$manifest.source_sha256.mapmaster
    $expectedCoords = [string]$manifest.source_sha256.mapcoords
    $expectedLua = [string]$manifest.source_sha256.map_lua

    if ($actualMaster -ne $expectedMaster -or
        $actualCoords -ne $expectedCoords -or
        $actualLua -ne $expectedLua) {
        throw 'Exact diagnostic restore hash verification failed.'
    }

    @(
        'result=LEGENDARY_TEST_ROUTE_MARKER_RESTORED'
        "target_catalogue_id=$($manifest.target_catalogue_id)"
        "mapmaster_sha256=$actualMaster"
        "mapcoords_sha256=$actualCoords"
        "mapmenu_sha256=$actualLua"
        'exact_restore=true'
        'save_or_progression_written=false'
        'raven_progression_modified=false'
    ) | Set-Content -LiteralPath (Join-Path $evidence 'result.txt') -Encoding UTF8
}
finally {
    Stop-Transcript | Out-Null
}

Remove-Item -LiteralPath $backupRoot -Recurse -Force

& git add -f -- $relativeEvidence
if ($LASTEXITCODE -ne 0) { throw 'git add diagnostic restore evidence failed.' }
& git commit -m "research(v0.10.5): restore temporary Legendary route marker $stamp" -- $relativeEvidence
if ($LASTEXITCODE -ne 0) { throw 'git commit diagnostic restore evidence failed.' }
& git push origin $ExpectedBranch
if ($LASTEXITCODE -ne 0) { throw 'git push diagnostic restore evidence failed.' }
$head = (& git rev-parse HEAD).Trim()

Write-Host ''
Write-Host "LEGENDARY_TEST_ROUTE_MARKER_RESTORED_AND_PUSHED $head" -ForegroundColor Green
